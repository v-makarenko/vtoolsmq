package com.fiveamsolutions.vtools.service;

import com.fiveamsolutions.vtools.web.rest.dto.TestDto;
import com.rabbitmq.client.*;
import com.rabbitmq.client.impl.StrictExceptionHandler;
import org.json.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/**
 * Service class for managing users.
 */
@Service
public class MQService {

    private final Logger log = LoggerFactory.getLogger(MQService.class);

    @Autowired
    private AmqpTemplate template;

    private String requestQueueName = "rpc_queue";


    public String summ(TestDto testDto) throws Exception {
        Object obj = template.convertSendAndReceive(requestQueueName, new JSONObject(testDto).toString());
        if (obj instanceof String) {
            return (String) obj;
        } else {
            return new String((byte[]) obj);
        }
    }

//    public static void main(String[] args) throws Exception {
//        TestDto dto = new TestDto();
//        dto.setName("Vladimir");
//        dto.setA(5);
//        dto.setB(3);
//        System.out.println(new MQService().summ(dto));
//    }
}
