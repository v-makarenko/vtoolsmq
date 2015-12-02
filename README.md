#Install guide

1. install python 2.7
2. install rabbit mq from the official site
3. pip install pika
4. pip install jep
4. start rabbitmq
5. run ./src/main/resources/qtools/start.py 
6. mvn install:install-file -Dfile=./lib/jep-3.4.2.jar -DgroupId=jep -DartifactId=jep -Dversion=3.4.2 -Dpackaging=jar
7. in build.gradle set jvmArgs=['-Djava.library.path='path/to/your/jep.so/or/jep.dll']. jep.so/jep.dll should appear in .../python2.7/.../site-packages/.../jep/
8. run gradlew

POST localhost:8080/api/test/jep to test jep

POST localhost:8080/api/test/mq to test mq way

test dto: { "a": 1, "b" : 1. "name" : "Vladimir" }
    
