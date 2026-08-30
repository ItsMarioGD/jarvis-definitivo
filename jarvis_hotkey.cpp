#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <iostream>
#include <string>

#pragma comment(lib, "ws2_32.lib")

// Jarvis Global Hotkey Listener
// Compilación: g++ jarvis_hotkey.cpp -o jarvis_hotkey.exe -lws2_32 -mwindows

void SendWakeSignal() {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) return;

    SOCKET sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock == INVALID_SOCKET) {
        WSACleanup();
        return;
    }

    sockaddr_in serverAddr;
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(9999);
    inet_pton(AF_INET, "127.0.0.1", &serverAddr.sin_addr);

    std::string msg = "WAKE_JARVIS";
    sendto(sock, msg.c_str(), msg.length(), 0, (SOCKADDR*)&serverAddr, sizeof(serverAddr));

    closesocket(sock);
    WSACleanup();
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {
    // Register Hotkey: Ctrl (2) + Alt (1) = MOD_CONTROL | MOD_ALT (3), 'J' (0x4A)
    // Usamos 1 como ID del hotkey
    if (RegisterHotKey(NULL, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x4A)) {
        // std::cout << "Jarvis Hotkey Registered: Ctrl + Alt + J" << std::endl;
    } else {
        return 1;
    }

    MSG msg = {0};
    while (GetMessage(&msg, NULL, 0, 0) != 0) {
        if (msg.message == WM_HOTKEY) {
            SendWakeSignal();
        }
    }

    UnregisterHotKey(NULL, 1);
    return 0;
}
