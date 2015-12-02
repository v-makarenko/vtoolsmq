package com.fiveamsolutions.vtools.web.rest.dto;

import javax.sql.rowset.serial.SerialArray;
import java.io.*;

/**
 * Created by VMakarenko on 30.11.2015.
 */
public class TestDto implements Serializable {
    private Integer a;
    private Integer b;
    private String name;

    public Integer getA() {
        return a;
    }

    public void setA(Integer a) {
        this.a = a;
    }

    public Integer getB() {
        return b;
    }

    public void setB(Integer b) {
        this.b = b;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

}

