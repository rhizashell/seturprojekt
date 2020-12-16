import flask
import json

import threading
import serial

import gpiozero

import time
import datetime

import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


app = flask.Flask(__name__)

try:
    pump = gpiozero.LED(26)
except gpiozero.exc.BadPinFactory:
    class Pump():
        def on(self):
            print(f"{datetime.datetime.utcnow()} - pump on")

        def off(self):
            print(f"{datetime.datetime.utcnow()} - pump off")

    pump = Pump()

obs = []

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_jobstore('sqlalchemy', url='sqlite:///scheduler.db')
scheduler.start()

class ReadSerialThread(threading.Thread):
    def __init__(self, path):
        threading.Thread.__init__(self)

        self.ser = serial.Serial(path, 9600, timeout=1)
        self.ser.flush()

        self.header = ['temp', 'humid', 'light']
        self.id = 1

    def run(self):
        while True:
            if self.ser.in_waiting > 0:
                item = {}
                row = self.ser.readline().decode('utf-8').rstrip().split(',')

                item['id'] = self.id
                self.id += 1

                for i in range(len(self.header)):
                    item[self.header[i]] = row[i]

                obs.append(item)

try:
    ReadSerialThread('/dev/ttyACM0').start()
except serial.serialutil.SerialException:
    pass

@app.route('/', methods=['GET'])
def getData():
    return json.dumps(obs)

@app.route('/<int:id>', methods=['GET'])
def getDataId(id):
    result = None

    for item in obs:
        if item['id'] == id:
            result = item

    return json.dumps(result)

@app.route('/<int:idFrom>/<int:idTo>', methods=['GET'])
def getDataFromTo(idFrom, idTo):
    result = []

    for item in obs:
        if (item['id'] >= idFrom) and (item['id'] <= idTo):
            result.append(item)

    return json.dumps(result)

@app.route('/pump', methods=['POST'])
def setPumpState():
    statusCode = 0
    try:
        data = flask.request.get_json(force=True)

        if int(data['state']) == 1:
            pump.on()
        elif int(data['state']) == 0:
            pump.off()
        else:
            raise ValueError

        return json.dumps({'status': f"{data['state']}"})
    except ValueError:
        statusCode = -1
    except:
        statusCode = -2
    return json.dumps({'status': statusCode})

def runPump(pumpInterval):
    pump.on()
    time.sleep(pumpInterval)
    pump.off()

@app.route('/cron/add', methods=['POST'])
def addJob():
    statusCode = 0
    # try:
    data = flask.request.get_json(force=True)
    pumpInterval = int(data['pumpInterval'])
    crontab = str(data['crontab'])

    print(pumpInterval, crontab)

    if pumpInterval > 0:
        # scheduler.add_job(
        #     lambda: runPump(pumpInterval),
        #     CronTrigger.from_crontab(crontab),
        #     id = '1'
        # )
        scheduler.add_job(
            func = runPump,
            args = [pumpInterval],
            trigger = CronTrigger.from_crontab(crontab),
            id = '1'
        )
        print('job started')
    else:
        raise ValueError

    return json.dumps({'status': 0})
    # except ValueError:
    #     statusCode = -1
    # except:
    #     statusCode = -2
    # return json.dumps({'status': statusCode})

@app.route('/cron/remove', methods=['POST'])
def removeJob():
    statusCode = 0
    try:
        scheduler.remove_job('1')
        print(f"job stopped")

        return json.dumps({'status': 0})
    except ValueError:
        statusCode = -1
    except:
        statusCode = -2
    return json.dumps({'status': statusCode})

if __name__ == '__main__':
    atexit.register(lambda: scheduler.shutdown())
    app.run()
