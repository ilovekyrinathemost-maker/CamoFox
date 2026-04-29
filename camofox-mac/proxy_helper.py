#!/usr/bin/env python3
"""CamoFox Mac — Transparent Proxy Helper.

A local transparent proxy that accepts connections redirected by macOS pfctl
and forwards them through the iPhone's SOCKS5 proxy.  Used in "force mode"
to catch ALL TCP traffic, including apps that ignore system proxy settings.

Architecture::

    [App] --pfctl rdr--> [proxy_helper :12345] --SOCKS5--> [iPhone :9876] --> Internet

On macOS, when pfctl redirects a connection with ``rdr pass``, the *original*
destination address is available via ``getsockname()`` on the accepted socket
(because the kernel rewrites the destination but the socket remembers).

Usage::

    python3 proxy_helper.py                           # defaults
    python3 proxy_helper.py --socks-host 192.168.1.5  # explicit iPhone IP
    python3 proxy_helper.py --listen-port 12345        # custom local port
    python3 proxy_helper.py --kill-switch              # block on proxy failure

Requires: Python 3.7+ (ships with macOS via Xcode CLT)
Dependencies: None (stdlib only)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import socket
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ProxyHelperConfig:
    """All tuneable knobs."""
    listen_host: str = "127.0.0.1"
    listen_port: int = 12345
    socks_host: str = ""          # auto-detect or set explicitly
    socks_port: int = 9876
    buffer_size: int = 65536
    connect_timeout: float = 10.0
    idle_timeout: float = 300.0
    max_connections: int = 1024
    kill_switch: bool = False
    log_level: str = "INFO"
    state_dir: str = os.path.expanduser("~/.camofox")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    """Runtime statistics."""
    start_time: float = 0.0
    active_connections: int = 0
    total_connections: int = 0
    total_bytes_in: int = 0
    total_bytes_out: int = 0
    total_errors: int = 0
    last_error: str = ""
    proxy_reachable: bool = True

    @property
    def uptime(self) -> str:
        secs = int(time.time() - self.start_time)
        h, secs = divmod(secs, 3600)
        m, s = divmod(secs, 60)
        return f"{h}h {m}m {s}s"


# ---------------------------------------------------------------------------
# SOCKS5 client implementation (stdlib only)
# ---------------------------------------------------------------------------

async def socks5_connect(
    socks_host: str,
    socks_port: int,
    target_host: str,
    target_port: int,
    timeout: float = 10.0,
) -> tuple:
    """Open a TCP connection to target via SOCKS5 proxy.

    Returns (reader, writer) asyncio streams.
    """
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(socks_host, socks_port),
        timeout=timeout,
    )

    # --- SOCKS5 greeting ---
    # Version 5, 1 auth method, 0x00 = no authentication
    writer.write(b"\x05\x01\x00")
    await writer.drain()

    greeting_resp = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
    if greeting_resp[0] != 0x05:
        writer.close()
        raise ConnectionError(f"Not a SOCKS5 proxy (version={greeting_resp[0]})")
    if greeting_resp[1] != 0x00:
        writer.close()
        raise ConnectionError(f"SOCKS5 auth method rejected ({greeting_resp[1]})")

    # --- SOCKS5 CONNECT request ---
    # Try to parse as IPv4 first, fall back to domain name
    try:
        addr_bytes = socket.inet_aton(target_host)
        # Version 5, CMD connect, RSV, ATYP IPv4
        req = b"\x05\x01\x00\x01" + addr_bytes + struct.pack("!H", target_port)
    except OSError:
        # Domain name addressing
        encoded = target_host.encode("ascii")
        req = (
            b"\x05\x01\x00\x03"
            + bytes([len(encoded)])
            + encoded
            + struct.pack("!H", target_port)
        )

    writer.write(req)
    await writer.drain()

    # --- SOCKS5 CONNECT response ---
    resp_header = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
    if resp_header[1] != 0x00:
        errcodes = {
            0x01: "general failure",
            0x02: "connection not allowed",
            0x03: "network unreachable",
            0x04: "host unreachable",
            0x05: "connection refused",
            0x06: "TTL expired",
            0x07: "command not supported",
            0x08: "address type not supported",
        }
        err = errcodes.get(resp_header[1], f"unknown ({resp_header[1]})")
        writer.close()
        raise ConnectionError(f"SOCKS5 connect failed: {err}")

    # Consume the bound address depending on address type
    atyp = resp_header[3]
    if atyp == 0x01:  # IPv4
        await reader.readexactly(4 + 2)
    elif atyp == 0x03:  # Domain
        domain_len = (await reader.readexactly(1))[0]
        await reader.readexactly(domain_len + 2)
    elif atyp == 0x04:  # IPv6
        await reader.readexactly(16 + 2)
    else:
        writer.close()
        raise ConnectionError(f"Unknown SOCKS5 address type: {atyp}")

    return reader, writer


# ---------------------------------------------------------------------------
# Bidirectional pipe
# ---------------------------------------------------------------------------

async def pipe(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    label: str,
    stats: Stats,
    direction: str,  # "in" or "out"
    buffer_size: int = 65536,
):
    """Copy data from reader to writer until EOF."""
    try:
        while True:
            data = await reader.read(buffer_size)
            if not data:
                break
            writer.write(data)
            await writer.drain()
            n = len(data)
            if direction == "in":
                stats.total_bytes_in += n
            else:
                stats.total_bytes_out += n
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    except Exception as e:
        logging.debug("pipe %s error: %s", label, e)
    finally:
        with contextlib.suppress(Exception):
            writer.close()


# ---------------------------------------------------------------------------
# Connection handler
# ---------------------------------------------------------------------------

async def handle_connection(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    config: ProxyHelperConfig,
    stats: Stats,
):
    """Handle a single redirected connection."""
    stats.active_connections += 1
    stats.total_connections += 1

    # Get original destination.
    # When pfctl uses "rdr pass", the original destination is preserved
    # in the socket.  On macOS we retrieve it via getsockname() on the
    # *accepted* socket before the kernel updates it.
    sock = client_writer.get_extra_info("socket")
    peername = client_writer.get_extra_info("peername", ("?", 0))

    # For macOS pfctl rdr: the original destination is what the client
    # tried to connect to.  With 'rdr pass on lo0', the accepted socket's
    # local address IS the original destination because macOS preserves it.
    # However for a more reliable approach, we use the PF_DIVERT approach
    # or simply read from /dev/pf.  For simplicity and reliability:
    #
    # Actually, on macOS with `rdr pass on lo0 proto tcp from any to !127.0.0.0/8 -> 127.0.0.1 port 12345`
    # the accepted socket's getsockname() returns 127.0.0.1:12345 (the redirected addr),
    # but we need the ORIGINAL destination.
    #
    # The standard macOS approach is to use the PF ioctl DIOCNATLOOK.
    # We implement this below.
    
    orig_dst = None
    if sock is not None:
        orig_dst = _get_original_dst_pf(sock, peername)
    
    if orig_dst is None:
        # Fallback: try getsockname (works in some pfctl configurations)
        local = client_writer.get_extra_info("sockname", ("127.0.0.1", 0))
        if local[0] != "127.0.0.1" and local[0] != "::1":
            orig_dst = local
        else:
            logging.warning("Cannot determine original destination for %s", peername)
            stats.total_errors += 1
            stats.active_connections -= 1
            client_writer.close()
            return

    target_host, target_port = orig_dst[0], orig_dst[1]
    logging.info("%s -> %s:%d", peername, target_host, target_port)

    try:
        # Connect to target through SOCKS5
        remote_reader, remote_writer = await socks5_connect(
            config.socks_host,
            config.socks_port,
            target_host,
            target_port,
            timeout=config.connect_timeout,
        )
        stats.proxy_reachable = True

        # Bidirectional pipe
        label = f"{peername}->{target_host}:{target_port}"
        await asyncio.gather(
            pipe(client_reader, remote_writer, f"{label}:out", stats, "out", config.buffer_size),
            pipe(remote_reader, client_writer, f"{label}:in", stats, "in", config.buffer_size),
        )

    except ConnectionError as e:
        logging.warning("SOCKS5 error for %s:%d: %s", target_host, target_port, e)
        stats.total_errors += 1
        stats.proxy_reachable = False
        stats.last_error = str(e)
    except asyncio.TimeoutError:
        logging.warning("Timeout connecting to %s:%d via SOCKS5", target_host, target_port)
        stats.total_errors += 1
        stats.last_error = "connection timeout"
    except Exception as e:
        logging.warning("Error handling %s:%d: %s", target_host, target_port, e)
        stats.total_errors += 1
        stats.last_error = str(e)
    finally:
        stats.active_connections -= 1
        with contextlib.suppress(Exception):
            client_writer.close()


# ---------------------------------------------------------------------------
# macOS PF NAT lookup (DIOCNATLOOK)
# ---------------------------------------------------------------------------

def _get_original_dst_pf(
    sock: socket.socket,
    peername: tuple,
) -> Optional[tuple]:
    """Use macOS PF's DIOCNATLOOK ioctl to find the original destination.

    This queries /dev/pf to look up the NAT state entry for the connection,
    which tells us where the client originally intended to connect.
    """
    import ctypes
    import ctypes.util

    try:
        # Open /dev/pf
        pf_fd = os.open("/dev/pf", os.O_RDONLY)
    except PermissionError:
        logging.debug("Cannot open /dev/pf — need root for DIOCNATLOOK")
        return None
    except FileNotFoundError:
        logging.debug("/dev/pf not found")
        return None

    try:
        # struct pfioc_natlook for macOS
        # This is platform-specific.  On macOS (Darwin), the structure is:
        #
        # struct pf_addr { union { struct in_addr, struct in6_addr, u_int32_t[4] } }
        # struct pfioc_natlook {
        #     struct pf_addr saddr;     /* 16 bytes */
        #     struct pf_addr daddr;     /* 16 bytes */
        #     struct pf_addr rsaddr;    /* 16 bytes */
        #     struct pf_addr rdaddr;    /* 16 bytes */
        #     u_int16_t sport;          /* 2 bytes */
        #     u_int16_t dport;          /* 2 bytes */
        #     u_int16_t rsport;         /* 2 bytes */
        #     u_int16_t rdport;         /* 2 bytes */
        #     sa_family_t af;           /* 1 byte */
        #     u_int8_t proto;           /* 1 byte */
        #     u_int8_t direction;       /* 1 byte */
        #     u_int8_t pad[1];          /* 1 byte */
        # };
        #
        # Total: 64 + 8 + 4 = 76 bytes (aligned)
        #
        # DIOCNATLOOK = _IOWR('D', 23, struct pfioc_natlook)
        # On macOS: _IOWR = 0xC0000000 | (size << 16) | (ord('D') << 8) | nr

        peer_ip = peername[0]
        peer_port = peername[1]
        local = sock.getsockname()
        local_ip = local[0]
        local_port = local[1]

        # Pack pfioc_natlook
        # saddr (source = client peer) — 16 bytes, only first 4 used for IPv4
        saddr = socket.inet_aton(peer_ip) + b"\x00" * 12
        # daddr (destination = our listen addr as seen by PF) — 16 bytes
        daddr = socket.inet_aton(local_ip) + b"\x00" * 12
        # rsaddr, rdaddr — will be filled by kernel
        rsaddr = b"\x00" * 16
        rdaddr = b"\x00" * 16

        sport = struct.pack("!H", peer_port)
        dport = struct.pack("!H", local_port)
        rsport = b"\x00\x00"
        rdport = b"\x00\x00"

        af = struct.pack("B", socket.AF_INET)  # 2
        proto = struct.pack("B", socket.IPPROTO_TCP)  # 6
        direction = struct.pack("B", 1)  # PF_IN = 1  (was PF_OUT on some systems)
        pad = b"\x00"

        natlook = saddr + daddr + rsaddr + rdaddr + sport + dport + rsport + rdport + af + proto + direction + pad

        # DIOCNATLOOK ioctl number for macOS
        # _IOWR('D', 23, 76) on macOS (64-bit)
        import fcntl

        DIOCNATLOOK = 0xC04C4417  # Pre-computed for macOS
        # Note: the exact value depends on struct size.  76 = 0x4C.
        # _IOWR = 0xC0000000 | (0x4C << 16) | (0x44 << 8) | 23
        # = 0xC0000000 | 0x004C0000 | 0x00004400 | 0x00000017
        # = 0xC04C4417

        result = bytearray(natlook)
        try:
            fcntl.ioctl(pf_fd, DIOCNATLOOK, result)
        except OSError as e:
            # Try PF_OUT direction
            direction = struct.pack("B", 2)  # PF_OUT = 2
            natlook = saddr + daddr + rsaddr + rdaddr + sport + dport + rsport + rdport + af + proto + direction + pad
            result = bytearray(natlook)
            try:
                fcntl.ioctl(pf_fd, DIOCNATLOOK, result)
            except OSError:
                logging.debug("DIOCNATLOOK failed: %s", e)
                return None

        # Parse rdaddr (bytes 48-64) and rdport (bytes 70-72)
        rd_addr_bytes = result[48:52]
        rd_port_bytes = result[70:72]

        orig_ip = socket.inet_ntoa(rd_addr_bytes)
        orig_port = struct.unpack("!H", rd_port_bytes)[0]

        if orig_ip == "0.0.0.0" or orig_port == 0:
            return None

        logging.debug("DIOCNATLOOK: %s:%d -> %s:%d", peer_ip, peer_port, orig_ip, orig_port)
        return (orig_ip, orig_port)

    except Exception as e:
        logging.debug("PF natlook error: %s", e)
        return None
    finally:
        os.close(pf_fd)


# ---------------------------------------------------------------------------
# Health monitor
# ---------------------------------------------------------------------------

async def health_check_loop(config: ProxyHelperConfig, stats: Stats):
    """Periodically check if the SOCKS5 proxy is reachable."""
    state_file = os.path.join(config.state_dir, "proxy_state")
    os.makedirs(config.state_dir, exist_ok=True)

    while True:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(config.socks_host, config.socks_port),
                timeout=5.0,
            )
            # Quick SOCKS5 handshake
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            resp = await asyncio.wait_for(reader.read(2), timeout=5.0)
            writer.close()

            if resp == b"\x05\x00":
                stats.proxy_reachable = True
                with open(state_file, "w") as f:
                    f.write("up")
            else:
                stats.proxy_reachable = False
                with open(state_file, "w") as f:
                    f.write("down")
        except Exception:
            stats.proxy_reachable = False
            with open(state_file, "w") as f:
                f.write("down")

        await asyncio.sleep(30)


# ---------------------------------------------------------------------------
# Status writer
# ---------------------------------------------------------------------------

async def status_writer(config: ProxyHelperConfig, stats: Stats):
    """Write status to a file for camofox-mac.sh to read."""
    status_file = os.path.join(config.state_dir, "proxy_helper_status")

    while True:
        try:
            with open(status_file, "w") as f:
                f.write(f"uptime={stats.uptime}\n")
                f.write(f"active={stats.active_connections}\n")
                f.write(f"total={stats.total_connections}\n")
                f.write(f"bytes_in={stats.total_bytes_in}\n")
                f.write(f"bytes_out={stats.total_bytes_out}\n")
                f.write(f"errors={stats.total_errors}\n")
                f.write(f"proxy_reachable={stats.proxy_reachable}\n")
                f.write(f"last_error={stats.last_error}\n")
        except Exception:
            pass
        await asyncio.sleep(5)


# ---------------------------------------------------------------------------
# Main server
# ---------------------------------------------------------------------------

async def run_server(config: ProxyHelperConfig):
    """Start the transparent proxy server."""
    stats = Stats(start_time=time.time())
    sem = asyncio.Semaphore(config.max_connections)

    async def on_connect(reader, writer):
        async with sem:
            await handle_connection(reader, writer, config, stats)

    server = await asyncio.start_server(
        on_connect,
        host=config.listen_host,
        port=config.listen_port,
        reuse_address=True,
    )

    # Write PID file
    pid_file = os.path.join(config.state_dir, "proxy_helper.pid")
    os.makedirs(config.state_dir, exist_ok=True)
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    logging.info("CamoFox transparent proxy listening on %s", addrs)
    logging.info("Forwarding via SOCKS5 %s:%d", config.socks_host, config.socks_port)

    # Start background tasks
    tasks = [
        asyncio.create_task(health_check_loop(config, stats)),
        asyncio.create_task(status_writer(config, stats)),
    ]

    try:
        await server.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        for t in tasks:
            t.cancel()
        server.close()
        await server.wait_closed()
        # Cleanup PID file
        with contextlib.suppress(Exception):
            os.unlink(pid_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> ProxyHelperConfig:
    parser = argparse.ArgumentParser(
        description="CamoFox Mac — Transparent Proxy Helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 proxy_helper.py --socks-host 192.168.1.5
  python3 proxy_helper.py --listen-port 12345 --kill-switch
  python3 proxy_helper.py --log-level DEBUG
""",
    )
    parser.add_argument("--listen-host", default="127.0.0.1",
                        help="Local bind address (default: 127.0.0.1)")
    parser.add_argument("--listen-port", type=int, default=12345,
                        help="Local listen port (default: 12345)")
    parser.add_argument("--socks-host", default="",
                        help="iPhone SOCKS5 proxy host (auto-detect if empty)")
    parser.add_argument("--socks-port", type=int, default=9876,
                        help="iPhone SOCKS5 proxy port (default: 9876)")
    parser.add_argument("--buffer-size", type=int, default=65536,
                        help="I/O buffer size (default: 65536)")
    parser.add_argument("--connect-timeout", type=float, default=10.0,
                        help="SOCKS5 connect timeout (default: 10s)")
    parser.add_argument("--max-connections", type=int, default=1024,
                        help="Max concurrent connections (default: 1024)")
    parser.add_argument("--kill-switch", action="store_true",
                        help="Block traffic if proxy is unreachable")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level (default: INFO)")
    parser.add_argument("--state-dir", default=os.path.expanduser("~/.camofox"),
                        help="State directory (default: ~/.camofox)")

    args = parser.parse_args()
    return ProxyHelperConfig(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        socks_host=args.socks_host,
        socks_port=args.socks_port,
        buffer_size=args.buffer_size,
        connect_timeout=args.connect_timeout,
        max_connections=args.max_connections,
        kill_switch=args.kill_switch,
        log_level=args.log_level,
        state_dir=args.state_dir,
    )


def main():
    config = parse_args()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not config.socks_host:
        logging.error("No SOCKS host specified.  Use --socks-host or run camofox-mac.sh")
        sys.exit(1)

    # Handle signals
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: loop.stop())

    try:
        loop.run_until_complete(run_server(config))
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
        logging.info("Transparent proxy stopped.")


if __name__ == "__main__":
    main()
