package com.fiveamsolutions.vtools.web.rest;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.LoggerContext;
import com.codahale.metrics.annotation.Timed;
import com.fiveamsolutions.vtools.service.JepService;
import com.fiveamsolutions.vtools.service.MQService;
import com.fiveamsolutions.vtools.web.rest.dto.LoggerDTO;
import com.fiveamsolutions.vtools.web.rest.dto.TestDto;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.stream.Collectors;

/**
 * Controller for view and managing Log Level at runtime.
 */
@RestController
@RequestMapping("/api/test")
public class TestResource {
    @Autowired
    private JepService jepService;
    @Autowired
    private MQService mqService;

    @RequestMapping(value = "jep",
        method = RequestMethod.POST)
    public String jepTest(@RequestBody TestDto dto) throws Exception {
        return jepService.summ(dto);
    }
    @RequestMapping(value = "mq",
        method = RequestMethod.POST)
    public String mqTest(@RequestBody TestDto dto) throws Exception {
        return mqService.summ(dto);
    }
}
