# Dolphin on the Nothing Phone 3

The Android phone runs a llama.cpp HTTP server; the PC uses its chat UI and
OpenAI-compatible API at `http://127.0.0.1:9931/`. The model is
`/sdcard/Download/Dolphin3.0-Llama3.1-8B-Q4_K_M.gguf`.

The executable and its shared libraries live in `/data/local/tmp/llama-b11913`.
ADB's shell can execute there, but cannot execute the build from Termux's private
directory because Android isolates that app's files. Run this server as the ADB
shell user, with `LD_LIBRARY_PATH` pointing to the deployed libraries.

## Start and check from the PC

With the phone reachable through ADB, run from the repository:

```sh
scripts/dolphin_up.sh
```

This connects to the phone, restores the port forward, starts the server if its
API is down, waits for it to answer, and opens the chat window. Use `--no-open`
for unattended recovery. Check the API with:

```sh
curl -f http://127.0.0.1:9931/v1/models
```

The tunnel is `adb forward tcp:9931 tcp:9931` (the script adds `-s SERIAL` to
select the phone). The server binds to the phone's loopback address; clients on
the PC reach it through the forwarded PC loopback port.

## Phone-side start command

Run the following inside `adb -s SERIAL shell`:

```sh
cd /data/local/tmp/llama-b11913
LD_LIBRARY_PATH=/data/local/tmp/llama-b11913 setsid nohup ./llama-server \
  -m /sdcard/Download/Dolphin3.0-Llama3.1-8B-Q4_K_M.gguf \
  -c 2048 -t 6 --host 127.0.0.1 --port 9931 \
  >/sdcard/Download/dolphin-server.log 2>&1 </dev/null &
```

`setsid` and `nohup` detach the process so an ADB session ending or `adb tcpip`
restarting adbd does not kill an ordinary background child. Startup errors and
server output go to `/sdcard/Download/dolphin-server.log`.

## Discovery and automatic recovery

[`scripts/dolphin_up.sh`](../scripts/dolphin_up.sh) tries, in order:

1. An already-connected wireless ADB transport.
2. `adb mdns services`, selecting an `_adb._tcp` service and connecting to its
   advertised address and port.
3. The last saved phone IP at port 5555, stored in
   `${MEGAZWORD_HOME:-$HOME/.megazword}/dolphin-phone.ip`.
4. An authorized USB connection, using `adb tcpip 5555` and reading the phone's
   current Wi-Fi address from `wlan0`.

mDNS discovers the current endpoint instead of pinning a DHCP address or debugging
port. When that advertisement is available on the PC's network, a changed IP or
port self-heals on the next run. The script also recreates forwarding after a PC
ADB server restart and restarts the phone server when the API is unavailable.

The installed user units are `~/.config/systemd/user/dolphin-tunnel.service` and
`dolphin-tunnel.timer`. The service runs this repository's script with
`--no-open`; the timer first runs after 45 seconds and repeats every 120 seconds.
To enable or inspect it:

```sh
systemctl --user enable --now dolphin-tunnel.timer
systemctl --user status dolphin-tunnel.timer
journalctl --user -u dolphin-tunnel.service -n 50
```

## Bring it back after a phone reboot

This setup's `adb tcpip 5555` mode does not persist across a phone reboot. The
server process also stops. Network discovery cannot re-enable an ADB listener
that is no longer running, so recovery requires **one USB connection after each
phone reboot** to put adbd back into TCP mode.

1. Unlock the phone, reconnect it to Wi-Fi, and plug it into the PC over USB.
   Keep USB debugging enabled and accept the PC's debugging authorization if
   prompted. `adb devices` must show the USB device as `device`.
2. Run `scripts/dolphin_up.sh --no-open`. Its USB fallback enables TCP debugging,
   learns the Wi-Fi address, connects wirelessly, restores the forward, and starts
   llama.cpp. Wait for the command to succeed.
3. Confirm `curl -f http://127.0.0.1:9931/v1/models` succeeds, then unplug USB.
   Run `scripts/dolphin_up.sh` to open chat. The timer maintains the connection
   while wireless ADB remains available.

If automatic USB recovery cannot read `wlan0` after adbd restarts, use the phone's
current Wi-Fi IP explicitly:

```sh
adb -s USB_SERIAL tcpip 5555
adb connect PHONE_WIFI_IP:5555
scripts/dolphin_up.sh --no-open
```

## Why generation is roughly 9 tokens per second

For this 8B Q4 model, single-stream token generation is capped mainly by memory
**bandwidth**, rather than CPU core count. Each new token requires reading roughly
the quantized model's several gigabytes of weights from memory. Effective memory
bandwidth divided by the bytes read per token bounds the generation rate; compute,
quantization overhead, and memory contention reduce it further.

The phone gets roughly 9 tok/s in this setup. Adding cores or increasing `-t 6`
cannot make the shared memory interface deliver weights faster once it is
saturated. Prompt processing can behave differently because it batches work;
temperature, context length, and other phone activity can also change observed
generation speed. Treat 9 tok/s as an approximate operating rate, not a guaranteed
hardware specification.
