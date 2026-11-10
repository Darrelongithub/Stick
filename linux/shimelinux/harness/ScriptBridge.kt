// SPDX-License-Identifier: BSD-3-Clause
// Test-only replacement for Nashorn. Production ShimeLinux keeps its Nashorn.
package com.group_finity.mascot.script

import com.group_finity.mascot.Mascot
import com.group_finity.mascot.action.ActionBase
import com.group_finity.mascot.exception.VariableException
import java.io.BufferedReader
import java.io.BufferedWriter

class Script(private val source: String?, private val clearAtInitFrame: Boolean) : Variable() {
    internal val scriptSource: String? get() = source
    internal val clearsAtInitFrame: Boolean get() = clearAtInitFrame
    private var value: Any? = null
    override fun init() { value = null }
    override fun initFrame() { if (clearAtInitFrame) value = null }
    override fun get(variables: VariableMap): Any? = value ?: evaluate(variables).also { value = it }
    override fun toString(): String = if (clearAtInitFrame) "#{$source}" else "\${$source}"

    private fun evaluate(variables: VariableMap): Any? {
        val mascot = variables.rawMap["mascot"]?.get(variables) as? Mascot
        val action = variables.rawMap["action"]?.get(variables) as? ActionBase
        val constants = variables.rawMap.filter { (key, _) -> key != "mascot" && key != "action" }
        fun q(text: String): String = "\"" + text
            .replace("\\", "\\\\").replace("\"", "\\\"")
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\""
        fun scalar(value: Any?): String = when (value) {
            null -> "null"
            is Boolean -> value.toString()
            is Number -> value.toString()
            else -> q(value.toString())
        }
        val json = buildString {
            append("{\"source\":").append(q(source ?: ""))
            append(",\"anchor\":{\"x\":").append(mascot?.anchor?.x ?: 0)
            append(",\"y\":").append(mascot?.anchor?.y ?: 1080).append("}")
            append(",\"totalCount\":").append(mascot?.totalCount ?: 0)
            append(",\"count\":").append(mascot?.count ?: 0)
            append(",\"time\":").append(mascot?.time ?: 0)
            append(",\"lookRight\":").append(mascot?.isLookRight ?: false)
            append(",\"actionTime\":").append(action?.time ?: 0)
            append(",\"variables\":{")
            append(constants.entries.joinToString(",") { (key, variable) ->
                q(key) + ":" + if (variable is Script) {
                    "{\"__script\":" + q(variable.scriptSource ?: "") +
                        ",\"__clear\":" + variable.clearsAtInitFrame + "}"
                } else scalar(variable.get(variables))
            })
            append("}}")
        }
        val response = ScriptProcess.call(json)
        val prefix = "{\"value\":"
        if (!response.startsWith(prefix) || !response.endsWith("}")) {
            throw VariableException("Headless script bridge failed: $response")
        }
        val raw = response.removePrefix(prefix).dropLast(1)
        return when {
            raw == "null" -> null
            raw == "true" -> true
            raw == "false" -> false
            raw.startsWith("\"") -> raw.substring(1, raw.length - 1)
                .replace("\\\"", "\"").replace("\\\\", "\\")
            else -> raw.toDoubleOrNull() ?: throw VariableException("Non-scalar script result: $raw")
        }
    }
}

private object ScriptProcess {
    private var process: Process? = null
    private var reader: BufferedReader? = null
    private var writer: BufferedWriter? = null
    @Synchronized fun call(json: String): String {
        if (process?.isAlive != true) {
            process = ProcessBuilder("node", System.getProperty("ava.scriptBridge")).start()
            reader = process!!.inputStream.bufferedReader()
            writer = process!!.outputStream.bufferedWriter()
        }
        writer!!.write(json.replace("\n", " "))
        writer!!.newLine()
        writer!!.flush()
        return reader!!.readLine() ?: error("headless script bridge exited")
    }
}
