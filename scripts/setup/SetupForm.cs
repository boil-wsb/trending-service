using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Windows.Forms;

namespace TrendingServiceSetup
{
    /// <summary>
    /// Trending Service Windows 服务安装/卸载程序
    /// 使用 Windows 内置 .NET Framework 编译，无需额外依赖。
    /// </summary>
    internal static class Program
    {
        [DllImport("kernel32.dll")]
        private static extern bool FreeConsole();

        [DllImport("kernel32.dll")]
        private static extern bool AttachConsole(int pid);

        private const int ATTACH_PARENT_PROCESS = -1;

        [STAThread]
        private static void Main(string[] args)
        {
            // 命令行模式：支持 -install / -uninstall / -status / -help
            if (args.Length > 0)
            {
                // 尝试附加到父进程控制台（从 cmd/powershell 启动时）
                AttachConsole(ATTACH_PARENT_PROCESS);
                RunCommandLine(args);
                return;
            }

            // GUI 模式：隐藏控制台窗口
            FreeConsole();

            // 自动提权
            if (!IsAdministrator())
            {
                RestartAsAdmin();
                return;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupForm());
        }

        // ===== 管理员权限 =====

        private static bool IsAdministrator()
        {
            using (var identity = WindowsIdentity.GetCurrent())
            {
                var principal = new WindowsPrincipal(identity);
                return principal.IsInRole(WindowsBuiltInRole.Administrator);
            }
        }

        private static void RestartAsAdmin()
        {
            var exePath = Application.ExecutablePath;
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = exePath,
                    Verb = "runas",
                    UseShellExecute = true
                });
            }
            catch
            {
                MessageBox.Show("需要管理员权限才能安装/卸载服务。", "权限不足",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        // ===== 命令行模式 =====

        private static void RunCommandLine(string[] args)
        {
            var manager = new ServiceManager();
            string action = args[0].ToLower().TrimStart('-', '/');

            switch (action)
            {
                case "install":
                    if (!EnsureAdmin()) return;
                    string projectPath = args.Length > 1 ? args[1] : GetDefaultProjectPath();
                    bool ok = manager.Install(projectPath);
                    Console.WriteLine(ok ? "[OK] 服务安装成功" : "[FAIL] 服务安装失败");
                    Environment.ExitCode = ok ? 0 : 1;
                    break;

                case "uninstall":
                    if (!EnsureAdmin()) return;
                    bool ok2 = manager.Uninstall();
                    Console.WriteLine(ok2 ? "[OK] 服务卸载成功" : "[FAIL] 服务卸载失败");
                    Environment.ExitCode = ok2 ? 0 : 1;
                    break;

                case "status":
                    var status = manager.GetStatus();
                    Console.WriteLine(status);
                    Environment.ExitCode = 0;
                    break;

                default:
                    PrintUsage();
                    break;
            }
        }

        private static bool EnsureAdmin()
        {
            if (!IsAdministrator())
            {
                Console.WriteLine("[ERROR] 需要管理员权限。请以管理员身份运行。");
                Environment.ExitCode = 1;
                return false;
            }
            return true;
        }

        private static void PrintUsage()
        {
            Console.WriteLine("Trending Service 安装程序 - 用法:");
            Console.WriteLine();
            Console.WriteLine("  TrendingServiceSetup.exe                  启动 GUI 界面（自动提权）");
            Console.WriteLine("  TrendingServiceSetup.exe -install [路径]  安装服务（需管理员权限）");
            Console.WriteLine("  TrendingServiceSetup.exe -uninstall        卸载服务（需管理员权限）");
            Console.WriteLine("  TrendingServiceSetup.exe -status           查看服务状态");
            Console.WriteLine("  TrendingServiceSetup.exe -help             显示此帮助信息");
            Console.WriteLine();
            Console.WriteLine("示例:");
            Console.WriteLine("  TrendingServiceSetup.exe -install \"D:\\MYDATA\\Include\\trending-service\"");
        }

        private static string GetDefaultProjectPath()
        {
            // 默认尝试从 exe 所在位置向上查找项目根目录
            var dir = new FileInfo(Application.ExecutablePath).DirectoryName;
            while (dir != null && dir.Length > 3)
            {
                if (File.Exists(Path.Combine(dir, "src", "main.py")) &&
                    File.Exists(Path.Combine(dir, "config.yaml")))
                {
                    return dir;
                }
                dir = Directory.GetParent(dir).FullName;
            }
            return @"D:\MYDATA\Include\trending-service";
        }
    }

    // ===== GUI 窗体 =====

    internal class SetupForm : Form
    {
        private TextBox _pathBox;
        private RichTextBox _logBox;
        private Button _installBtn;
        private Button _uninstallBtn;
        private Button _browseBtn;
        private Button _openReportBtn;
        private Button _statusBtn;

        public SetupForm()
        {
            InitializeUI();
        }

        private void InitializeUI()
        {
            Text = "Trending Service 安装程序";
            Width = 640;
            Height = 520;
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;

            // === 项目路径 ===
            var pathLabel = new Label
            {
                Text = "项目路径:",
                Location = new System.Drawing.Point(20, 20),
                Size = new System.Drawing.Size(80, 20),
                TextAlign = System.Drawing.ContentAlignment.MiddleLeft
            };

            _pathBox = new TextBox
            {
                Location = new System.Drawing.Point(100, 18),
                Size = new System.Drawing.Size(420, 22),
                Text = Program_GetDefaultPath()
            };

            _browseBtn = new Button
            {
                Text = "浏览...",
                Location = new System.Drawing.Point(530, 16),
                Size = new System.Drawing.Size(80, 26)
            };
            _browseBtn.Click += BrowseBtn_Click;

            // === 按钮区 ===
            _installBtn = new Button
            {
                Text = "安装服务",
                Location = new System.Drawing.Point(20, 55),
                Size = new System.Drawing.Size(120, 36),
                FlatStyle = FlatStyle.Flat,
                BackColor = System.Drawing.Color.FromArgb(46, 139, 87),
                ForeColor = System.Drawing.Color.White
            };
            _installBtn.Click += InstallBtn_Click;

            _uninstallBtn = new Button
            {
                Text = "卸载服务",
                Location = new System.Drawing.Point(150, 55),
                Size = new System.Drawing.Size(120, 36),
                FlatStyle = FlatStyle.Flat,
                BackColor = System.Drawing.Color.FromArgb(220, 80, 80),
                ForeColor = System.Drawing.Color.White
            };
            _uninstallBtn.Click += UninstallBtn_Click;

            _statusBtn = new Button
            {
                Text = "查看状态",
                Location = new System.Drawing.Point(280, 55),
                Size = new System.Drawing.Size(100, 36),
                FlatStyle = FlatStyle.Flat
            };
            _statusBtn.Click += StatusBtn_Click;

            _openReportBtn = new Button
            {
                Text = "打开报告",
                Location = new System.Drawing.Point(390, 55),
                Size = new System.Drawing.Size(100, 36),
                FlatStyle = FlatStyle.Flat,
                Enabled = false
            };
            _openReportBtn.Click += OpenReportBtn_Click;

            // === 日志区 ===
            var logLabel = new Label
            {
                Text = "操作日志:",
                Location = new System.Drawing.Point(20, 100),
                Size = new System.Drawing.Size(100, 20)
            };

            _logBox = new RichTextBox
            {
                Location = new System.Drawing.Point(20, 120),
                Size = new System.Drawing.Size(590, 340),
                ReadOnly = true,
                Font = new System.Drawing.Font("Consolas", 9),
                BackColor = System.Drawing.Color.FromArgb(30, 30, 30),
                ForeColor = System.Drawing.Color.FromArgb(220, 220, 220)
            };

            Controls.AddRange(new Control[] {
                pathLabel, _pathBox, _browseBtn,
                _installBtn, _uninstallBtn, _statusBtn, _openReportBtn,
                logLabel, _logBox
            });

            AcceptButton = _installBtn;
        }

        private string Program_GetDefaultPath()
        {
            var dir = new FileInfo(Application.ExecutablePath).DirectoryName;
            while (dir != null && dir.Length > 3)
            {
                if (File.Exists(Path.Combine(dir, "src", "main.py")) &&
                    File.Exists(Path.Combine(dir, "config.yaml")))
                {
                    return dir;
                }
                try { dir = Directory.GetParent(dir).FullName; }
                catch { break; }
            }
            return @"D:\MYDATA\Include\trending-service";
        }

        private void BrowseBtn_Click(object sender, EventArgs e)
        {
            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择 Trending Service 项目根目录";
                if (Directory.Exists(_pathBox.Text))
                    dialog.SelectedPath = _pathBox.Text;
                if (dialog.ShowDialog() == DialogResult.OK)
                {
                    _pathBox.Text = dialog.SelectedPath;
                }
            }
        }

        private void InstallBtn_Click(object sender, EventArgs e)
        {
            string projectPath = _pathBox.Text.Trim().TrimEnd('"', ' ');
            if (string.IsNullOrEmpty(projectPath))
            {
                Log("ERROR: 请输入项目路径", true);
                return;
            }

            SetButtonsEnabled(false);
            _logBox.Clear();

            var manager = new ServiceManager();
            manager.LogCallback = Log;

            try
            {
                bool ok = manager.Install(projectPath);
                if (ok)
                {
                    Log("");
                    Log("========================================", false, System.Drawing.Color.LimeGreen);
                    Log("  服务安装并启动成功！", false, System.Drawing.Color.LimeGreen);
                    Log("========================================", false, System.Drawing.Color.LimeGreen);
                    Log("");
                    Log("访问报告: http://localhost:8888/report.html");
                    Log("服务管理: services.msc (服务名: TrendingService)");
                    _openReportBtn.Enabled = true;
                }
                else
                {
                    Log("");
                    Log("========================================", true, System.Drawing.Color.OrangeRed);
                    Log("  服务安装失败，请查看上方日志", true, System.Drawing.Color.OrangeRed);
                    Log("========================================", true, System.Drawing.Color.OrangeRed);
                }
            }
            catch (Exception ex)
            {
                Log("ERROR: " + ex.Message, true);
            }
            finally
            {
                SetButtonsEnabled(true);
            }
        }

        private void UninstallBtn_Click(object sender, EventArgs e)
        {
            SetButtonsEnabled(false);
            _logBox.Clear();

            var manager = new ServiceManager();
            manager.LogCallback = Log;

            try
            {
                bool ok = manager.Uninstall();
                if (ok)
                {
                    Log("");
                    Log("========================================", false, System.Drawing.Color.LimeGreen);
                    Log("  服务已成功卸载", false, System.Drawing.Color.LimeGreen);
                    Log("========================================", false, System.Drawing.Color.LimeGreen);
                    _openReportBtn.Enabled = false;
                }
                else
                {
                    Log("");
                    Log("  卸载过程出现问题，请查看上方日志", true, System.Drawing.Color.OrangeRed);
                }
            }
            catch (Exception ex)
            {
                Log("ERROR: " + ex.Message, true);
            }
            finally
            {
                SetButtonsEnabled(true);
            }
        }

        private void StatusBtn_Click(object sender, EventArgs e)
        {
            _logBox.Clear();
            var manager = new ServiceManager();
            manager.LogCallback = Log;
            string status = manager.GetStatus();
            Log(status);
        }

        private void OpenReportBtn_Click(object sender, EventArgs e)
        {
            try
            {
                Process.Start("http://localhost:8888/report.html");
            }
            catch { }
        }

        private void SetButtonsEnabled(bool enabled)
        {
            _installBtn.Enabled = enabled;
            _uninstallBtn.Enabled = enabled;
            _statusBtn.Enabled = enabled;
            _browseBtn.Enabled = enabled;
            _pathBox.Enabled = enabled;
        }

        private void Log(string message)
        {
            Log(message, false, System.Drawing.Color.FromArgb(220, 220, 220));
        }

        private void Log(string message, bool isError)
        {
            Log(message, isError, isError ? System.Drawing.Color.OrangeRed : System.Drawing.Color.FromArgb(220, 220, 220));
        }

        private void Log(string message, bool isError, System.Drawing.Color color)
        {
            if (_logBox.InvokeRequired)
            {
                _logBox.Invoke(new Action(() => AppendLog(message, color)));
            }
            else
            {
                AppendLog(message, color);
            }
        }

        private void AppendLog(string message, System.Drawing.Color color)
        {
            _logBox.SelectionStart = _logBox.TextLength;
            _logBox.SelectionLength = 0;
            _logBox.SelectionColor = color;
            _logBox.AppendText(message + Environment.NewLine);
            _logBox.ScrollToCaret();
        }
    }

    // ===== 服务管理核心逻辑 =====

    internal class ServiceManager
    {
        private const string ServiceName = "TrendingService";
        private const string ServiceDescription = "Trending Service - 热点信息采集与A股行情服务 (http://localhost:8888)";

        public Action<string> LogCallback;

        private void Log(string msg)
        {
            if (LogCallback != null) LogCallback(msg);
        }

        public bool Install(string projectPath)
        {
            projectPath = projectPath.Trim().TrimEnd('\\', '"', ' ');
            Log("[1/8] 验证项目路径...");
            if (!Directory.Exists(projectPath))
            {
                Log("  ERROR: 目录不存在 - " + projectPath);
                return false;
            }

            string pythonExe = Path.Combine(projectPath, "venv", "Scripts", "pythonw.exe");
            string mainScript = Path.Combine(projectPath, "src", "main.py");
            string nssmExe = Path.Combine(projectPath, "vendor", "nssm", "nssm.exe");

            if (!File.Exists(pythonExe))
            {
                Log("  ERROR: Python 解释器不存在 - " + pythonExe);
                Log("  请先创建虚拟环境: python -m venv venv");
                return false;
            }
            if (!File.Exists(mainScript))
            {
                Log("  ERROR: 启动脚本不存在 - " + mainScript);
                return false;
            }
            if (!File.Exists(nssmExe))
            {
                Log("  WARNING: nssm 不存在，尝试下载... - " + nssmExe);
                if (!DownloadNssm(nssmExe))
                {
                    Log("  ERROR: nssm 下载失败，请手动下载 nssm.exe 到 vendor/nssm/ 目录");
                    return false;
                }
            }
            Log("  OK - 路径验证通过");

            // 停止旧服务
            Log("[2/8] 检查并停止旧服务...");
            if (ServiceExists())
            {
                StopService();
                RunCommand(nssmExe, "remove " + ServiceName + " confirm");
                System.Threading.Thread.Sleep(2000);
                Log("  OK - 旧服务已移除");
            }
            else
            {
                Log("  OK - 无旧服务");
            }

            // 停止占用端口的进程
            Log("[3/8] 清理端口 8888 占用...");
            KillPortOccupant(8888);
            Log("  OK");

            // 清理 PID 文件
            string pidFile = Path.Combine(projectPath, "trending_service.pid");
            if (File.Exists(pidFile))
            {
                try { File.Delete(pidFile); } catch { }
            }

            // 注册服务
            Log("[4/8] 注册 Windows 服务...");
            int ret = RunCommand(nssmExe, "install " + ServiceName + " \"" + pythonExe + "\" \"" + mainScript + "\"");
            if (ret != 0)
            {
                Log("  ERROR: nssm install 失败 (code=" + ret + ")");
                return false;
            }
            Log("  OK - 服务已注册");

            // 配置参数
            Log("[5/8] 配置服务参数...");
            RunCommand(nssmExe, "set " + ServiceName + " AppDirectory \"" + projectPath + "\"");
            RunCommand(nssmExe, "set " + ServiceName + " Start SERVICE_AUTO_START");
            RunCommand(nssmExe, "set " + ServiceName + " AppExit Default Restart");
            RunCommand(nssmExe, "set " + ServiceName + " AppRestartDelay 60000");
            RunCommand(nssmExe, "set " + ServiceName + " Description \"" + ServiceDescription + "\"");

            string logDir = Path.Combine(projectPath, "data", "logs");
            if (!Directory.Exists(logDir))
            {
                Directory.CreateDirectory(logDir);
            }
            RunCommand(nssmExe, "set " + ServiceName + " AppStdout \"" + Path.Combine(logDir, "service_nssm_stdout.log") + "\"");
            RunCommand(nssmExe, "set " + ServiceName + " AppStderr \"" + Path.Combine(logDir, "service_nssm_stderr.log") + "\"");
            RunCommand(nssmExe, "set " + ServiceName + " AppRotateFiles 1");
            RunCommand(nssmExe, "set " + ServiceName + " AppRotateBytes 10485760");
            Log("  OK - 自动启动 + 崩溃重启(60s) + 日志轮转(10MB)");

            // 启动服务
            Log("[6/8] 启动服务...");
            try
            {
                using (var sc = new ServiceController(ServiceName))
                {
                    sc.Start();
                    sc.WaitForStatus(ServiceControllerStatus.Running, TimeSpan.FromSeconds(15));
                    Log("  OK - 服务状态: " + sc.Status);
                }
            }
            catch (Exception ex)
            {
                Log("  WARNING: 启动异常 - " + ex.Message);
                Log("  请稍后通过 services.msc 手动启动");
            }

            // 创建快捷方式
            Log("[7/8] 创建开始菜单快捷方式...");
            CreateShortcut(projectPath);
            Log("  OK - 开始菜单 > Trending Service > 访问报告");

            // 验证 API
            Log("[8/8] 验证 API...");
            System.Threading.Thread.Sleep(8000);
            if (CheckApi())
            {
                Log("  OK - http://localhost:8888/api/status 响应正常");
            }
            else
            {
                Log("  WARNING: API 未就绪，服务可能仍在初始化中");
                Log("  请稍后访问 http://localhost:8888/report.html");
            }

            return true;
        }

        public bool Uninstall()
        {
            string projectPath = GetProjectPathFromService();

            Log("[1/4] 检查服务状态...");
            if (!ServiceExists())
            {
                Log("  服务 " + ServiceName + " 不存在，无需卸载");
                return true;
            }
            Log("  OK - 服务存在");

            Log("[2/4] 停止服务...");
            StopService();
            Log("  OK");

            string nssmExe = null;
            if (projectPath != null)
            {
                nssmExe = Path.Combine(projectPath, "vendor", "nssm", "nssm.exe");
            }
            if (nssmExe == null || !File.Exists(nssmExe))
            {
                nssmExe = "nssm.exe"; // 尝试 PATH
            }

            Log("[3/4] 删除服务...");
            int ret = RunCommand(nssmExe, "remove " + ServiceName + " confirm");
            if (ret != 0)
            {
                Log("  WARNING: nssm remove 返回 code=" + ret + "，尝试 sc delete...");
                RunCommand("sc.exe", "delete " + ServiceName);
            }
            System.Threading.Thread.Sleep(2000);
            Log("  OK - 服务已删除");

            Log("[4/4] 删除快捷方式...");
            DeleteShortcut();
            Log("  OK");

            Log("");
            Log("服务已完全卸载。");

            return true;
        }

        public string GetStatus()
        {
            var sb = new StringBuilder();
            sb.AppendLine("=== Trending Service 状态 ===");
            sb.AppendLine();

            // 服务状态
            if (ServiceExists())
            {
                try
                {
                    using (var sc = new ServiceController(ServiceName))
                    {
                        sb.AppendLine("服务名称: " + ServiceName);
                        sb.AppendLine("服务状态: " + sc.Status);
                        sb.AppendLine("启动类型: " + sc.StartType);
                    }
                }
                catch (Exception ex)
                {
                    sb.AppendLine("服务状态查询异常: " + ex.Message);
                }
            }
            else
            {
                sb.AppendLine("服务状态: 未安装");
            }

            sb.AppendLine();

            // API 状态
            sb.AppendLine("API 地址: http://localhost:8888");
            if (CheckApi())
            {
                sb.AppendLine("API 状态: 正常");
            }
            else
            {
                sb.AppendLine("API 状态: 不可达");
            }

            sb.AppendLine();

            // 项目路径
            string projectPath = GetProjectPathFromService();
            if (projectPath != null)
            {
                sb.AppendLine("项目路径: " + projectPath);
            }

            return sb.ToString();
        }

        // ===== 辅助方法 =====

        private bool ServiceExists()
        {
            try
            {
                using (var sc = new ServiceController(ServiceName))
                {
                    var status = sc.Status;
                    return true;
                }
            }
            catch
            {
                return false;
            }
        }

        private void StopService()
        {
            try
            {
                using (var sc = new ServiceController(ServiceName))
                {
                    if (sc.Status == ServiceControllerStatus.Running)
                    {
                        sc.Stop();
                        sc.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(10));
                    }
                }
            }
            catch { }
        }

        private int RunCommand(string fileName, string arguments)
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = fileName,
                    Arguments = arguments,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                using (var p = Process.Start(psi))
                {
                    p.WaitForExit(15000);
                    return p.ExitCode;
                }
            }
            catch
            {
                return -1;
            }
        }

        private void KillPortOccupant(int port)
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "netstat.exe",
                    Arguments = "-ano",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true
                };
                using (var p = Process.Start(psi))
                {
                    string output = p.StandardOutput.ReadToEnd();
                    p.WaitForExit(5000);

                    foreach (string line in output.Split('\n'))
                    {
                        if (line.Contains(":" + port + " ") && line.Contains("LISTENING"))
                        {
                            var parts = line.Trim().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
                            if (parts.Length > 0)
                            {
                                int pid;
                                if (int.TryParse(parts[parts.Length - 1], out pid) && pid > 0)
                                {
                                    try { Process.GetProcessById(pid).Kill(); } catch { }
                                }
                            }
                        }
                    }
                }
            }
            catch { }
        }

        private bool CheckApi()
        {
            try
            {
                var request = System.Net.WebRequest.Create("http://localhost:8888/api/status");
                request.Timeout = 8000;
                using (var response = request.GetResponse())
                {
                    return true;
                }
            }
            catch
            {
                return false;
            }
        }

        private void CreateShortcut(string projectPath)
        {
            try
            {
                string shortcutDir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.Programs),
                    "Trending Service");

                if (!Directory.Exists(shortcutDir))
                {
                    Directory.CreateDirectory(shortcutDir);
                }

                // 快捷方式 1: 访问报告
                CreateShortcutFile(
                    Path.Combine(shortcutDir, "访问报告.url"),
                    "http://localhost:8888/report.html");

                // 快捷方式 2: 项目目录
                CreateShortcutFile(
                    Path.Combine(shortcutDir, "项目目录.lnk"),
                    projectPath);

                // 快捷方式 3: 服务管理
                CreateShortcutFile(
                    Path.Combine(shortcutDir, "服务管理(services.msc).lnk"),
                    "services.msc");

                // 快捷方式 4: 卸载服务
                string exePath = Application.ExecutablePath;
                if (!string.IsNullOrEmpty(exePath))
                {
                    CreateShortcutFile(
                        Path.Combine(shortcutDir, "卸载服务.lnk"),
                        exePath,
                        "-uninstall");
                }
            }
            catch { }
        }

        private void CreateShortcutFile(string path, string target, string arguments = null)
        {
            try
            {
                if (path.EndsWith(".url"))
                {
                    File.WriteAllText(path,
                        "[InternetShortcut]" + Environment.NewLine +
                        "URL=" + target + Environment.NewLine,
                        Encoding.UTF8);
                }
                else
                {
                    // 使用 COM 创建 .lnk
                    var shellType = Type.GetTypeFromProgID("WScript.Shell");
                    if (shellType != null)
                    {
                        dynamic shell = Activator.CreateInstance(shellType);
                        dynamic shortcut = shell.CreateShortcut(path);
                        shortcut.TargetPath = target;
                        if (arguments != null)
                            shortcut.Arguments = arguments;
                        shortcut.Save();
                    }
                }
            }
            catch { }
        }

        private void DeleteShortcut()
        {
            try
            {
                string shortcutDir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.Programs),
                    "Trending Service");

                if (Directory.Exists(shortcutDir))
                {
                    Directory.Delete(shortcutDir, true);
                }
            }
            catch { }
        }

        private string GetProjectPathFromService()
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "sc.exe",
                    Arguments = "qc " + ServiceName,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true
                };
                using (var p = Process.Start(psi))
                {
                    string output = p.StandardOutput.ReadToEnd();
                    p.WaitForExit(5000);

                    // 解析 BINARY_PATH_NAME
                    foreach (string line in output.Split('\n'))
                    {
                        if (line.Contains("BINARY_PATH_NAME"))
                        {
                            // 格式: BINARY_PATH_NAME : "C:\...\pythonw.exe" "C:\...\src\main.py"
                            var match = System.Text.RegularExpressions.Regex.Match(
                                line, @"""([^""]*src[^\\""]*main\.py)""");
                            if (match.Success)
                            {
                                string mainPath = match.Groups[1].Value;
                                var fi = new FileInfo(mainPath);
                                if (fi.Directory != null && fi.Directory.Parent != null)
                                {
                                    return fi.Directory.Parent.FullName;
                                }
                            }
                        }
                    }
                }
            }
            catch { }
            return null;
        }

        private bool DownloadNssm(string targetPath)
        {
            // nssm 已存在时不下载
            if (File.Exists(targetPath)) return true;

            try
            {
                string dir = Path.GetDirectoryName(targetPath);
                if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);

                // 尝试从官方下载
                string[] urls = {
                    "https://nssm.cc/release/nssm-2.24.zip",
                    "https://github.com/kirillkovalenko/nssm/releases/download/nssm-2.24/nssm-2.24.zip"
                };

                string zipPath = Path.Combine(dir, "nssm.zip");
                foreach (string url in urls)
                {
                    try
                    {
                        var client = new System.Net.WebClient();
                        client.DownloadFile(url, zipPath);
                        break;
                    }
                    catch { }
                }

                if (!File.Exists(zipPath)) return false;

                // 解压（用 Shell.Application）
                var shellType = Type.GetTypeFromProgID("Shell.Application");
                if (shellType != null)
                {
                    dynamic shell = Activator.CreateInstance(shellType);
                    dynamic zipFolder = shell.NameSpace(zipPath);
                    dynamic destFolder = shell.NameSpace(dir);
                    destFolder.CopyHere(zipFolder.Items(), 16);
                    System.Threading.Thread.Sleep(2000);
                }

                // 查找 win64\nssm.exe
                string win64Nssm = Path.Combine(dir, "nssm-2.24", "win64", "nssm.exe");
                if (File.Exists(win64Nssm))
                {
                    File.Copy(win64Nssm, targetPath, true);
                }

                // 清理
                try { File.Delete(zipPath); } catch { }

                return File.Exists(targetPath);
            }
            catch
            {
                return false;
            }
        }
    }
}
