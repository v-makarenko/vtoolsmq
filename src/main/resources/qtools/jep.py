#!/usr/bin/env python
import pika
import json
import time


def getSum(name, a, b):
    return '' + name + ', your sum is ' + str(a+b)

