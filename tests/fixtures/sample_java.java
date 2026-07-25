package com.example;

import java.util.List;
import java.util.Map;

/**
 * A simple user with a name.
 */
public class SimpleClass {
    private String name;

    public SimpleClass(String name) {
        this.name = name;
    }

    /** Returns the stored value. */
    public String getValue() {
        return helperMethod(name).trim();
    }

    private static String helperMethod(String input) {
        return input.toUpperCase();
    }

    static class Nested {
        void nestedMethod() {}
    }
}

interface Repository {
    List<SimpleClass> findAll();
}

@interface Marker {}

enum Status {
    ACTIVE,
    INACTIVE
}

record Point(int x, int y) {
    double distance() {
        return Math.sqrt(x * x + y * y);
    }
}
