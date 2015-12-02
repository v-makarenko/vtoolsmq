package com.fiveamsolutions.vtools.service;

import com.fiveamsolutions.vtools.web.rest.dto.TestDto;
import jep.Jep;
import jep.JepException;
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
public class JepService {

    private final Logger log = LoggerFactory.getLogger(JepService.class);

    @Autowired
    private AmqpTemplate template;

    public String summ(TestDto testDto) throws Exception {
        try (Jep jep = new Jep()) {
            jep.runScript("./src/main/resources/qtools/jep.py");
            return (String) jep.getValue("getSum(':name', :a,:b)"
                .replace(":name", testDto.getName())
                .replace(":a", testDto.getA().toString())
                .replace(":b", testDto.getB().toString()));
        } catch (JepException e) {
            e.printStackTrace();
        }
        return null;
    }
}
