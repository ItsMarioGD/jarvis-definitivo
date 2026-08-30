package jarvis.android;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.IOException;

/**
 * JarvisAdbBridge - Conector Java para controlar dispositivos Android vía ADB
 * Sprint 6: Sandbox Móvil Android
 */
public class JarvisAdbBridge {

    /**
     * Ejecuta un comando ADB y retorna la salida.
     * @param command El comando adb a ejecutar (ej. "shell input keyevent 26" para pantalla).
     * @return Respuesta del comando o mensaje de error.
     */
    public static String executeAdbCommand(String command) {
        StringBuilder output = new StringBuilder();
        try {
            Process process = Runtime.getRuntime().exec("adb " + command);
            BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
            String line;
            while ((line = reader.readLine()) != null) {
                output.append(line).append("\n");
            }
            int exitCode = process.waitFor();
            if (exitCode != 0) {
                output.append("Error: Command exited with code ").append(exitCode);
            }
        } catch (IOException | InterruptedException e) {
            e.printStackTrace();
            return "Exception: " + e.getMessage();
        }
        return output.toString();
    }

    public static void main(String[] args) {
        if (args.length > 0) {
            String result = executeAdbCommand(String.join(" ", args));
            System.out.println(result);
        } else {
            System.out.println("Jarvis ADB Bridge Ready.");
            System.out.println("Connected devices:");
            System.out.println(executeAdbCommand("devices"));
        }
    }
}
