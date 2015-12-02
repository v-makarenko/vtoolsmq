#!/usr/bin/env python
import pika
import json
import time

connection = pika.BlockingConnection(pika.ConnectionParameters(
        host='localhost'))

channel = connection.channel()

channel.queue_declare(queue='rpc_queue')

def getSum(name, a, b):
    return '' + name + ', your sum is ' + str(a+b)

def on_request(ch, method, props, body):
    time.sleep(3)
    obj = json.loads(body)
    response = getSum(obj['name'], obj['a'], obj['b'])
    ch.basic_publish(exchange='',
                     routing_key=props.reply_to,
                     properties=pika.BasicProperties(correlation_id = \
                                                     props.correlation_id),
                     body=str(response))
    ch.basic_ack(delivery_tag = method.delivery_tag)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(on_request, queue='rpc_queue')

print " [x] Awaiting RPC requests"
channel.start_consuming()