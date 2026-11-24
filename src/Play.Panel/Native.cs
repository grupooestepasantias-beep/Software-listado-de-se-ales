using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace Play.Panel;

/// <summary>Funciones de Windows: tiempo sin usar mouse/teclado e inicio automático con Windows.</summary>
internal static class Native
{
    [StructLayout(LayoutKind.Sequential)]
    private struct LASTINPUTINFO
    {
        public uint cbSize;
        public uint dwTime;
    }

    [DllImport("user32.dll")]
    private static extern bool GetLastInputInfo(ref LASTINPUTINFO info);

    /// <summary>Tiempo desde la última pulsación de tecla o movimiento del mouse en esta sesión de Windows.</summary>
    public static TimeSpan TiempoInactivo()
    {
        var info = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf<LASTINPUTINFO>() };
        if (!GetLastInputInfo(ref info)) return TimeSpan.Zero;
        var ahora = unchecked((uint)Environment.TickCount);
        return TimeSpan.FromMilliseconds(unchecked(ahora - info.dwTime));
    }

    private const string ClaveRun = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string NombreRun = "Play";

    public static bool InicioConWindows()
    {
        using var k = Registry.CurrentUser.OpenSubKey(ClaveRun);
        return k?.GetValue(NombreRun) is string;
    }

    public static void InicioConWindows(bool activar)
    {
        using var k = Registry.CurrentUser.CreateSubKey(ClaveRun);
        if (activar && Environment.ProcessPath is { } exe) k.SetValue(NombreRun, $"\"{exe}\"");
        else k.DeleteValue(NombreRun, throwOnMissingValue: false);
    }
}
