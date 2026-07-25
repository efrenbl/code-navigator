package com.example

import kotlin.math.abs
import kotlin.collections.List

/**
 * Greets someone by name.
 */
fun greet(name: String): String {
    return formatName(abs(1).toString())
}

suspend fun fetchData(id: Int): String {
    return "data"
}

class SimpleClass(val name: String) {
    fun getValue(): String {
        return greet(name)
    }

    fun processData(items: List<String>): Int {
        return items.size
    }
}

data class Point(val x: Int, val y: Int)

open class Base

interface Repository {
    fun findAll(): List<SimpleClass>
}

fun interface Action {
    fun run()
}

enum class Status {
    ACTIVE,
    INACTIVE
}

object Singleton {
    fun instance(): Int {
        return 1
    }
}

typealias Handler = (String) -> Unit
