/**
 * Sample JavaScript file for testing the code mapper.
 */

// Constants
const MAX_RETRIES = 3;
const DEFAULT_TIMEOUT = 30;

/**
 * A simple function.
 */
function simpleFunction() {
    return "Hello, World!";
}

/**
 * An async function.
 * @param {string} url - The URL to fetch.
 * @returns {Promise<object>} The response data.
 */
async function asyncFunction(url) {
    const response = await fetch(url);
    return response.json();
}

/**
 * An arrow function.
 */
const arrowFunction = (x, y) => x + y;

/**
 * An async arrow function.
 */
const asyncArrowFunction = async (url) => {
    const data = await asyncFunction(url);
    return data;
};

/**
 * A class with methods.
 */
class SimpleClass {
    constructor(value) {
        this.value = value;
    }

    getValue() {
        return this.value;
    }

    setValue(value) {
        this.value = value;
    }
}

/**
 * A derived class.
 */
class DerivedClass extends SimpleClass {
    constructor(value, name) {
        super(value);
        this.name = name;
    }

    getName() {
        return this.name;
    }
}

module.exports = {
    simpleFunction,
    asyncFunction,
    arrowFunction,
    asyncArrowFunction,
    SimpleClass,
    DerivedClass
};
