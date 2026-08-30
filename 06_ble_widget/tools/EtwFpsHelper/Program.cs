using System;
using System.Diagnostics;
using System.IO;
using System.IO.MemoryMappedFiles;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace EtwFpsHelper
{
    class Program
    {
        [DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

        private const uint ERROR_SUCCESS = 0;
        private const uint EVENT_CONTROL_CODE_ENABLE_PROVIDER = 1;
        private const uint EVENT_CONTROL_CODE_DISABLE_PROVIDER = 0;
        private const uint EVENT_TRACE_CONTROL_FLUSH = 3;
        private const byte TRACE_LEVEL_INFORMATION = 4;
        private const uint PROCESS_TRACE_MODE_REAL_TIME = 0x00000100;
        private const uint PROCESS_TRACE_MODE_EVENT_RECORD = 0x10000000;
        private const uint PROCESS_TRACE_MODE_RAW_TIMESTAMP = 0x00001000;
        private const uint WNODE_FLAG_TRACED_GUID = 0x00020000;

        private static readonly bool IsWin10 = Environment.OSVersion.Version.Build < 22000;
        private static readonly Guid DxgKrnlProviderId = IsWin10
            ? new Guid("CA11C036-0102-4A2D-A6AD-F03CFED5D3C9")
            : new Guid("802EC45A-1E99-4B83-9920-87C98277BA9D");
        private static readonly Guid FlipProviderId = new Guid("802EC45A-1E99-4B83-9920-87C98277BA9D");

        private static readonly ushort EVENT_DXGKRNL_PRESENT_INFO = (ushort)(IsWin10 ? 42 : 184);
        private static readonly ulong DXGKRNL_KEYWORD_PRESENT = IsWin10 ? 0UL : 0x0000000008000000UL;

        private const uint EVENT_FILTER_TYPE_EVENT_ID = 0x80000200;
        private const uint ENABLE_TRACE_PARAMETERS_VERSION_2 = 2;
        private const string SessionName = "Esp32GpuFpsSession";

        [StructLayout(LayoutKind.Sequential)]
        private struct WNODE_HEADER
        {
            public uint BufferSize;
            public uint ProviderId;
            public ulong HistoricalContext;
            public ulong TimeStamp;
            public Guid Guid;
            public uint ClientContext;
            public uint Flags;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct EVENT_TRACE_PROPERTIES
        {
            public WNODE_HEADER Wnode;
            public uint BufferSize;
            public uint MinimumBuffers;
            public uint MaximumBuffers;
            public uint MaximumFileSize;
            public uint LogFileMode;
            public uint FlushTimer;
            public uint EnableFlags;
            public int AgeLimit;
            public uint NumberOfBuffers;
            public uint FreeBuffers;
            public uint EventsLost;
            public uint BuffersWritten;
            public uint LogBuffersLost;
            public uint RealTimeBuffersLost;
            public IntPtr LoggerThreadId;
            public uint LogFileNameOffset;
            public uint LoggerNameOffset;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 1024)]
            public string LoggerName;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 1024)]
            public string LogFileName;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct EVENT_RECORD
        {
            public EVENT_HEADER EventHeader;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct EVENT_HEADER
        {
            public ushort Size;
            public ushort HeaderType;
            public ushort Flags;
            public ushort EventProperty;
            public uint ThreadId;
            public uint ProcessId;
            public long TimeStamp;
            public Guid ProviderId;
            public ushort Id;
            public byte Version;
            public byte Channel;
            public byte Level;
            public byte Opcode;
            public ushort Task;
            public ulong Keyword;
            public uint KernelTime;
            public uint UserTime;
            public Guid ActivityId;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct EVENT_FILTER_DESCRIPTOR
        {
            public ulong Ptr;
            public uint Size;
            public uint Type;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct ENABLE_TRACE_PARAMETERS
        {
            public uint Version;
            public uint EnableProperty;
            public uint ControlFlags;
            public Guid SourceId;
            public IntPtr EnableFilterDesc;
            public uint FilterDescCount;
        }

        [StructLayout(LayoutKind.Explicit, Size = 448)]
        private struct EVENT_TRACE_LOGFILE
        {
            [FieldOffset(8)] public IntPtr LoggerName;
            [FieldOffset(28)] public uint ProcessTraceMode;
            [FieldOffset(400)] public IntPtr BufferCallback;
            [FieldOffset(424)] public IntPtr EventRecordCallback;
            [FieldOffset(440)] public IntPtr Context;
        }

        private delegate void EventRecordCallback([In] ref EVENT_RECORD eventRecord);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)]
        private static extern uint StartTrace(out long sessionHandle, string sessionName, ref EVENT_TRACE_PROPERTIES properties);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)]
        private static extern uint StopTrace(long sessionHandle, string sessionName, ref EVENT_TRACE_PROPERTIES properties);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)]
        private static extern uint ControlTrace(long sessionHandle, string? sessionName, ref EVENT_TRACE_PROPERTIES properties, uint controlCode);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)]
        private static extern uint EnableTraceEx2(long sessionHandle, in Guid providerId, uint controlCode, byte level, ulong matchAnyKeyword, ulong matchAllKeyword, uint timeout, IntPtr enableParameters);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)]
        private static extern ulong OpenTrace(ref EVENT_TRACE_LOGFILE logfile);

        [DllImport("advapi32.dll")]
        private static extern uint ProcessTrace(ulong[] handleArray, uint handleCount, IntPtr startTime, IntPtr endTime);

        [DllImport("advapi32.dll")]
        private static extern uint CloseTrace(ulong traceHandle);

        private const int RollingWindowSize = 360;
        private static readonly long[] _frameTimes = new long[RollingWindowSize];
        private static volatile int _frameHead = 0;
        private static volatile int _framesFilled = 0;
        private static volatile int _targetPid = 0;
        private static long _sessionHandle = 0;
        private static ulong _traceHandle = 0;
        private static EventRecordCallback? _callback;
        private static bool _running = true;

        static readonly string[] DesktopApps = new[] {
            "explorer", "shellexperiencehost", "searchhost", "taskmgr", "devenv", "code",
            "chrome", "msedge", "firefox", "powershell", "pwsh", "cmd", "conhost", "windowsterminal",
            "ghelper", "python", "py"
        };

        static void Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;
            Console.WriteLine("[ETW-FPS] Starting G-Helper ETW FPS Helper Service...");

            var traceThread = new Thread(TraceWorker) { IsBackground = true };
            traceThread.Start();

            // Create Shared Memory for Python
            using var mmf = MemoryMappedFile.CreateOrOpen("Esp32FpsSharedMem", 256);
            using var accessor = mmf.CreateViewAccessor();

            int lastFgPid = 0;
            int currentFps = 0;

            while (_running)
            {
                Thread.Sleep(300);

                GetWindowThreadProcessId(GetForegroundWindow(), out uint fgPidRaw);
                int fgPid = (int)fgPidRaw;

                if (fgPid != lastFgPid && fgPid > 0)
                {
                    lastFgPid = fgPid;
                    string pname = "";
                    try
                    {
                        using var p = Process.GetProcessById(fgPid);
                        pname = p.ProcessName.ToLower();
                    }
                    catch { }

                    bool isDesktop = false;
                    foreach (var app in DesktopApps)
                    {
                        if (pname.Contains(app))
                        {
                            isDesktop = true;
                            break;
                        }
                    }

                    if (isDesktop)
                    {
                        _targetPid = 0;
                        _framesFilled = 0;
                    }
                    else
                    {
                        _targetPid = fgPid;
                        _frameHead = 0;
                        _framesFilled = 0;
                    }
                }

                if (_targetPid > 0)
                {
                    currentFps = (int)Math.Round(SampleFps());
                }
                else
                {
                    currentFps = 0;
                }

                // Write to Shared Memory
                // offset 0: int fps (4 bytes)
                // offset 4: int pid (4 bytes)
                accessor.Write(0, currentFps);
                accessor.Write(4, _targetPid);
            }

            StopSession();
        }

        private static void TraceWorker()
        {
            try
            {
                var stopProps = BuildSessionProperties();
                StopTrace(0, SessionName, ref stopProps);

                var startProps = BuildSessionProperties();
                uint hr = StartTrace(out _sessionHandle, SessionName, ref startProps);
                if (hr != ERROR_SUCCESS)
                {
                    Console.WriteLine($"[ETW-FPS] StartTrace failed with code 0x{hr:X}");
                    return;
                }

                EnableProvider();

                _callback = OnEventRecord;
                var logfile = new EVENT_TRACE_LOGFILE
                {
                    LoggerName = Marshal.StringToHGlobalUni(SessionName),
                    ProcessTraceMode = PROCESS_TRACE_MODE_REAL_TIME | PROCESS_TRACE_MODE_EVENT_RECORD | PROCESS_TRACE_MODE_RAW_TIMESTAMP,
                    EventRecordCallback = Marshal.GetFunctionPointerForDelegate(_callback),
                };

                _traceHandle = OpenTrace(ref logfile);
                if (_traceHandle == 0 || _traceHandle == ulong.MaxValue)
                {
                    Console.WriteLine("[ETW-FPS] OpenTrace failed");
                    return;
                }

                var flushThread = new Thread(() =>
                {
                    while (_running && _sessionHandle != 0)
                    {
                        Thread.Sleep(200);
                        FlushSession();
                    }
                }) { IsBackground = true };
                flushThread.Start();

                var handles = new[] { _traceHandle };
                ProcessTrace(handles, 1, IntPtr.Zero, IntPtr.Zero);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[ETW-FPS] Trace error: {ex.Message}");
            }
        }

        private static void EnableProvider()
        {
            IntPtr desc = Marshal.AllocHGlobal(Marshal.SizeOf<EVENT_FILTER_DESCRIPTOR>());
            IntPtr eventIdBuf = Marshal.AllocHGlobal(8);
            IntPtr paramsPtr = Marshal.AllocHGlobal(Marshal.SizeOf<ENABLE_TRACE_PARAMETERS>());

            try
            {
                Marshal.WriteByte(eventIdBuf, 0, 1);
                Marshal.WriteByte(eventIdBuf, 1, 0);
                Marshal.WriteInt16(eventIdBuf, 2, 1);
                Marshal.WriteInt16(eventIdBuf, 4, (short)EVENT_DXGKRNL_PRESENT_INFO);

                Marshal.StructureToPtr(new EVENT_FILTER_DESCRIPTOR
                {
                    Ptr = (ulong)eventIdBuf.ToInt64(),
                    Size = 6,
                    Type = EVENT_FILTER_TYPE_EVENT_ID,
                }, desc, false);

                Marshal.StructureToPtr(new ENABLE_TRACE_PARAMETERS
                {
                    Version = ENABLE_TRACE_PARAMETERS_VERSION_2,
                    EnableFilterDesc = desc,
                    FilterDescCount = 1,
                }, paramsPtr, false);

                uint hr = EnableTraceEx2(_sessionHandle, DxgKrnlProviderId, EVENT_CONTROL_CODE_ENABLE_PROVIDER, TRACE_LEVEL_INFORMATION, DXGKRNL_KEYWORD_PRESENT, 0, 0, paramsPtr);
                if (hr != ERROR_SUCCESS)
                {
                    EnableTraceEx2(_sessionHandle, DxgKrnlProviderId, EVENT_CONTROL_CODE_ENABLE_PROVIDER, TRACE_LEVEL_INFORMATION, DXGKRNL_KEYWORD_PRESENT, 0, 0, IntPtr.Zero);
                }
            }
            finally
            {
                Marshal.FreeHGlobal(paramsPtr);
                Marshal.FreeHGlobal(eventIdBuf);
                Marshal.FreeHGlobal(desc);
            }
        }

        private static void FlushSession()
        {
            if (_sessionHandle == 0) return;
            var props = BuildSessionProperties();
            ControlTrace(_sessionHandle, null, ref props, EVENT_TRACE_CONTROL_FLUSH);
        }

        private static void StopSession()
        {
            _running = false;
            if (_traceHandle != 0) CloseTrace(_traceHandle);
            if (_sessionHandle != 0)
            {
                var props = BuildSessionProperties();
                StopTrace(_sessionHandle, SessionName, ref props);
            }
        }

        private static void OnEventRecord(ref EVENT_RECORD record)
        {
            if (record.EventHeader.ProviderId != DxgKrnlProviderId || record.EventHeader.Id != EVENT_DXGKRNL_PRESENT_INFO)
                return;

            int targetPid = _targetPid;
            if (targetPid <= 0 || (int)record.EventHeader.ProcessId != targetPid)
                return;

            _frameTimes[_frameHead] = record.EventHeader.TimeStamp;
            _frameHead = (_frameHead + 1) % RollingWindowSize;
            if (_framesFilled < RollingWindowSize) _framesFilled++;
        }

        private static double SampleFps()
        {
            int filled = _framesFilled;
            if (filled < 2) return 0;

            long freq = Stopwatch.Frequency;
            int head = _frameHead;
            long newest = _frameTimes[(head - 1 + RollingWindowSize) % RollingWindowSize];

            if (Stopwatch.GetTimestamp() - newest > 4 * freq) return 0;

            long cutoff = newest - freq;
            int count = 1;
            long oldest = newest;
            for (int i = 2; i <= filled; i++)
            {
                long t = _frameTimes[(head - i + RollingWindowSize) % RollingWindowSize];
                if (t < cutoff) break;
                oldest = t;
                count++;
            }

            double elapsed = (double)(newest - oldest) / freq;
            if (elapsed <= 0) return 0;
            return (count - 1) / elapsed;
        }

        private static EVENT_TRACE_PROPERTIES BuildSessionProperties() => new EVENT_TRACE_PROPERTIES
        {
            Wnode = new WNODE_HEADER
            {
                BufferSize = (uint)Marshal.SizeOf<EVENT_TRACE_PROPERTIES>(),
                Flags = WNODE_FLAG_TRACED_GUID,
                ClientContext = 1,
            },
            LogFileMode = 0x00000100,
            LogFileNameOffset = 0,
            LoggerNameOffset = (uint)Marshal.OffsetOf<EVENT_TRACE_PROPERTIES>(nameof(EVENT_TRACE_PROPERTIES.LoggerName)),
            BufferSize = 8,
            MinimumBuffers = 8,
            MaximumBuffers = 16,
        };
    }
}
