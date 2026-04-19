# PyQt + Ctrl+C：为什么终端按 Ctrl+C 杀不掉进程

> 复盘：为什么 `src/maxvoice/__main__.py` 在 `QApplication` 创建后要注册 SIGINT handler 和一个空转的 `QTimer`。

---

## TL;DR

- **症状**：在 iTerm 里 `python -m maxvoice` 启动后，按 Ctrl+C 没反应，进程不退出。只能通过 tray 菜单 Quit，或者系统 Force Quit。Force Quit 会触发 macOS 的崩溃报告弹窗。
- **根因**：Qt 的事件循环是 C++ 实现，进 `qapp.exec()` 后长期阻塞在系统调用（macOS 上是 `kevent`）里。Python 的信号机制依赖"解释器执行字节码时检查 flag"——循环不回到 Python，flag 就永远不被读，SIGINT 一直挂起。
- **修复**：
  1. 显式把 SIGINT 路由到 `qapp.quit()`，让它走正常的 `aboutToQuit` → `app.stop()` 清理流程。
  2. 加一个 200ms 的 no-op `QTimer`，强制解释器定期苏醒，把挂起的信号消费掉。
- **教训**：**任何长期驻留的 PyQt / PySide 程序都要装这个 workaround。**不是 bug，是 Python 信号模型和 Qt 事件循环的语义错配，社区多年来的标准做法。

---

## 症状是什么样的

用户报告：

> 我好像有时候不能正常退出 Python 的 CMD 界面。我开的是 iTerm，然后按 Ctrl+C，它并没有退出进程。现在只能通过 tray 菜单里点 Quit，或者点右下角 Python 图标 Force Quit。但是 Force Quit 的时候系统会提示 Report Bug 之类的，好像是异常终止了 Python 进程。

特征：
- Ctrl+C 完全无响应，不是"退出慢"，是根本不触发
- 如果恰好这时候有 GUI 事件（比如鼠标晃一下 tray 图标），Ctrl+C 有时候会迟到地生效——这是个很强的提示，说明信号被挂起而不是丢失
- Force Quit 后 macOS 弹 "Python quit unexpectedly" 的崩溃报告
- 崩溃报告里没有 Python traceback，因为进程是被 `SIGKILL` 硬切的，没跑任何 Python 清理代码

---

## 为什么 Ctrl+C 不生效

### Python 信号处理的实现细节

关键：**Python 的 signal handler 不是在 OS 递送信号的瞬间跑的。**

CPython 里流程是这样：

1. OS 递送 SIGINT → C 层的 low-level handler 被调用
2. 这个 low-level handler **只做一件事**：往一个全局 flag 写"有 SIGINT 待处理"
3. Python 解释器每执行一段字节码，会调用 `PyErr_CheckSignals()` 看这个 flag
4. 看到 flag 被置位 → 调用用户用 `signal.signal()` 注册的 Python handler

这个设计是有原因的：Python handler 是普通 Python 函数，可能分配内存、获取 GIL、调别的 C 扩展。在 OS 信号上下文里直接跑 Python 代码是极度不安全的（async-signal-safe 的函数少得可怜）。所以 CPython 选择延迟到"安全点"执行。

### Qt 事件循环的问题

`qapp.exec()` 进 Qt 的 C++ 事件循环。主循环大致是：

```
while not should_quit:
    events = platform_poll(timeout)   # macOS 上是 kevent，阻塞
    for ev in events:
        dispatch(ev)
```

`platform_poll` 是阻塞的系统调用。如果没有任何事件（鼠标没动、键盘没按、定时器没到期、socket 没数据），它就一直睡在内核里。

关键点：**整个循环体都在 C++ 里，解释器完全没机会跑任何字节码。**

于是：
- Ctrl+C 来了 → low-level handler 把 flag 置位 ✓
- 但 Python 不执行字节码 → `PyErr_CheckSignals()` 不被调用 ✗
- flag 永远没人读 → Python handler 不跑 ✗

信号不是丢了，是被"挂"在那里了。直到下一个 Qt 事件（比如你晃一下鼠标）让循环回到 Python 边界，信号才会被处理。

### 为什么 Force Quit 会报 crash

Force Quit 发 `SIGKILL`（或 `SIGTERM`）。`SIGKILL` 是不可捕获的，内核直接回收进程，Python 没任何机会跑清理代码。

`aboutToQuit` → `app.stop()` 里做了一堆事：
- 停掉音频采集线程
- 注销全局 `NSEvent` monitor
- 关掉 SQLite 连接

硬切的时候这些全是悬空状态，macOS 的 crash reporter 就会认为是"异常终止"，弹 Report Bug 弹窗。

---

## 修复方案

### 两段式 workaround

```python
import signal
from PyQt6.QtCore import QTimer

qapp = QApplication(sys.argv)
qapp.setQuitOnLastWindowClosed(False)

# 1. 把 SIGINT 路由到 Qt 的正常退出路径
signal.signal(signal.SIGINT, lambda *_: qapp.quit())

# 2. 一个什么都不做的 timer，强制解释器定期苏醒
sigint_timer = QTimer()
sigint_timer.start(200)
sigint_timer.timeout.connect(lambda: None)
```

### Timer 到底是怎么工作的

`QTimer.start(200)` 每 200ms 触发一次 `timeout` 信号。每次触发时：

1. Qt 从 `kevent` 里被定时器叫醒
2. 调用我们连上的 `lambda: None` ——**这是一个 Python 函数**
3. 调用 Python 函数就必须进入 Python 解释器
4. 解释器入口触发 `PyErr_CheckSignals()`
5. 发现 SIGINT flag → 跑 `lambda *_: qapp.quit()` → Qt 事件循环正常退出
6. `aboutToQuit` → `app.stop()` → 所有资源正常清理

`lambda: None` 的唯一作用就是**让解释器入口被触发一次**。函数体干什么不重要。

### 为什么是 200ms

- 太短（10ms）：每秒 100 次无意义调用，浪费 CPU，电池党会不爽
- 太长（2s）：Ctrl+C 按下去之后最多要等 2 秒才退，体感像卡死
- 200ms：延迟上限 200ms，人眼感知是"立刻"，CPU 开销忽略不计

这个值是 PyQt 社区的经验值，大部分示例都用 100-500ms 之间的数。

---

## 替代方案为什么不行

**方案 A：`signal.signal(SIGINT, signal.SIG_DFL)`**

直接让 SIGINT 走 OS 默认行为（终止进程）。确实能退出，但跟 Force Quit 一样是硬切，`aboutToQuit` 不会跑，音频线程、全局 monitor 都是悬空的。等于绕过问题而不是解决问题。

**方案 B：`signal.set_wakeup_fd()`**

Python 3.5+ 提供的 API，可以让 SIGINT 往一个 fd 写字节。理论上可以把这个 fd 接到 `QSocketNotifier` 上，让 Qt 事件循环醒来。但：
- 配置比 QTimer 方案复杂得多
- macOS 上 Qt 的 `QSocketNotifier` 有历史 bug
- 性能上跟 200ms timer 没任何可见差别

**方案 C：自己写个线程轮询**

复杂度爆炸，还要处理 GIL、线程间信号递送（默认只有主线程收信号），完全不值。

---

## 相关链接

- [Python docs: Execution of Python signal handlers](https://docs.python.org/3/library/signal.html#execution-of-python-signal-handlers)
- [Qt docs: QCoreApplication::exec()](https://doc.qt.io/qt-6/qcoreapplication.html#exec)
- [StackOverflow: How do I make CTRL-C stop a PyQt application?](https://stackoverflow.com/questions/4938723/) —— 这个问题有 15 年历史了，答案基本就是上面这套。
