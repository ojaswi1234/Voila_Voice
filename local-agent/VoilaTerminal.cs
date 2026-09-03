using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

class Program
{
    const uint ENABLE_QUICK_EDIT = 0x0040;
    const int STD_INPUT_HANDLE = -10;

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr GetStdHandle(int nStdHandle);

    [DllImport("kernel32.dll")]
    static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);

    [DllImport("kernel32.dll")]
    static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);

    static void DisableQuickEdit()
    {
        IntPtr consoleHandle = GetStdHandle(STD_INPUT_HANDLE);
        uint consoleMode;
        if (GetConsoleMode(consoleHandle, out consoleMode))
        {
            consoleMode &= ~ENABLE_QUICK_EDIT;
            SetConsoleMode(consoleHandle, consoleMode);
        }
    }

    static void Main(string[] args)
    {
        if (args.Length < 2) return;
        string b64Cmd = args[0];
        string outFile = args[1];
        
        DisableQuickEdit();
        Console.Title = "Voila AI - Terminal Tool";
        
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine("================================================");
        Console.WriteLine("          [AI] EXECUTING COMMAND");
        Console.WriteLine("================================================");
        Console.WriteLine();

        string actualCmd = "";
        try {
            actualCmd = Encoding.UTF8.GetString(Convert.FromBase64String(b64Cmd));
        } catch {
            actualCmd = b64Cmd;
        }

        Console.ForegroundColor = ConsoleColor.Green;
        Console.Write("PS> ");
        Console.ForegroundColor = ConsoleColor.Yellow;
        foreach (char c in actualCmd)
        {
            Console.Write(c);
            Thread.Sleep(2);
        }
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.DarkGray;
        Console.WriteLine("------------------------------------------------");
        Console.ResetColor();

        File.WriteAllText(outFile, "");
        object fileLock = new object();

        Process p = new Process();
        p.StartInfo.FileName = "cmd.exe";
        p.StartInfo.Arguments = "/c " + actualCmd;
        p.StartInfo.UseShellExecute = false;
        p.StartInfo.RedirectStandardOutput = true;
        p.StartInfo.RedirectStandardError = true;
        p.StartInfo.CreateNoWindow = true;

        DataReceivedEventHandler handler = (sender, e) => {
            if (e.Data != null) {
                Console.WriteLine(e.Data);
                lock(fileLock) {
                    File.AppendAllText(outFile, e.Data + Environment.NewLine);
                }
            }
        };

        p.OutputDataReceived += handler;
        p.ErrorDataReceived += handler;

        try {
            p.Start();
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            p.WaitForExit();
        } catch (Exception ex) {
            string err = "Execution Error: " + ex.Message;
            Console.WriteLine(err);
            lock(fileLock) {
                File.AppendAllText(outFile, err + Environment.NewLine);
            }
        }

        Console.ForegroundColor = ConsoleColor.DarkGray;
        Console.WriteLine();
        Console.WriteLine("[Finished] Closing in 4 seconds...");
        Thread.Sleep(4000);
    }
}
