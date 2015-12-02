#Install guide

1. install python 2.7
2. install rabbit mq from the official site
3. pip install pika
4. start rabbitmq
5. run resources/qtools/start.py
6. download jep.jar https://pypi.python.org/packages/source/j/jep/jep-3.4.2.tar.gz 
7. mvn install:install-file -Dfile=<path-to-file> -DgroupId=jep -DartifactId=jep -Dversion=3.4.2
6. run gradlew

POST localhost:8080/api/test/jep to test jep

POST localhost:8080/api/test/mq to test mq way

test dto: { "a": 1, "b" : 1. "name" : "Vladimir" }
    
