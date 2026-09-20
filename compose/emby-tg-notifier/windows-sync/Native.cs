using System;
using System.Text;
using System.Runtime.InteropServices;

public class JavSnapshot {
    public bool Present;
    public bool Valid;
    public long PositionMs;
    public long DurationMs;
    public string Title;
    public int State;
}

public static class JavPot {
    delegate bool EnumProc(IntPtr hwnd, IntPtr parameter);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc fn, IntPtr arg);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint msg, IntPtr w, IntPtr l, uint flags, uint timeout, out UIntPtr result);

    public static JavSnapshot Read(int pid, string marker) {
        var sample = new JavSnapshot();
        EnumWindows(delegate(IntPtr hwnd, IntPtr arg) {
            uint owner;
            GetWindowThreadProcessId(hwnd, out owner);
            if (owner != (uint)pid) return true;
            var title = new StringBuilder(1024);
            GetWindowText(hwnd, title, title.Capacity);
            if (title.Length == 0) return true;
            sample.Present = true;
            if (!title.ToString().Contains(marker)) return true;
            UIntPtr pos, duration, state;
            if (SendMessageTimeout(hwnd, 0x400, (IntPtr)0x5006, IntPtr.Zero, 2, 400, out state) == IntPtr.Zero) return true;
            sample.State = unchecked((int)state.ToUInt64());
            if (sample.State != 1 && sample.State != 2) return true;
            // PotPlayer WM_USER: milliseconds, lParam=1; timeouts prevent a hung player blocking sync.
            if (SendMessageTimeout(hwnd, 0x400, (IntPtr)0x5004, (IntPtr)1, 2, 400, out pos) == IntPtr.Zero) return true;
            if (SendMessageTimeout(hwnd, 0x400, (IntPtr)0x5002, (IntPtr)1, 2, 400, out duration) == IntPtr.Zero) return true;
            long p = unchecked((long)pos.ToUInt64());
            long d = unchecked((long)duration.ToUInt64());
            if (p < 0 || d <= 0 || p > d + 2000 || d > 1209600000) return true;
            sample.Valid = true;
            sample.PositionMs = p;
            sample.DurationMs = d;
            sample.Title = title.ToString();
            return false;
        }, IntPtr.Zero);
        return sample;
    }
}
