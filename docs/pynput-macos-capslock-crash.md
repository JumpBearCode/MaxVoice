# pynput + macOS + Caps Lock：一个会让进程秒崩的坑

> 复盘：为什么 `src/maxvoice/hotkey.py` 不再用 pynput，改用 PyObjC 的 `NSEvent` monitor。

---

## TL;DR

- **症状**：打开 Settings / History / Dictionary 任何一个 dialog 后按一下 **Caps Lock**，整个 MaxVoice 进程秒崩，没有 Python traceback。
- **根因**：pynput 在 macOS 上把全局键盘监听放在**后台线程**的 `CGEventTap` 回调里。这个回调里调用了 macOS 的 Text Services Manager (TSM)，而 TSM 严格要求**只能在主线程上调用**。新版 macOS 的 libdispatch 加了断言强制检查，错的线程上调用直接 `SIGTRAP` 杀进程。
- **修复**：把全局热键的实现从 `pynput.GlobalHotKeys` 换成 PyObjC 的 `NSEvent.addGlobalMonitorForEventsMatchingMask_handler_` + `addLocalMonitorForEventsMatchingMask_handler_`。两者都跑在主线程，从根上避开了线程错乱。
- **教训**：**任何 macOS 上的"全局键盘 hook"，如果是用 CGEventTap 在后台线程跑的，都要怀疑这个雷。**不是只有 pynput 有问题，而是这种实现模式本身在 modern macOS 上就是不安全的。

---

## 症状是什么样的

用户报告：

> 当我准备加字典的时候在打字的时候打到一半，我按了一下 Caps Lock，再打了一个字就自动退出了整个程序。

进一步实验确认：

> 如果我点开 Settings、History 或者 Dictionary，无论我是不是中文输入法，只要我按 Caps Lock，这个进程都会崩。

特征：
- 没有 Python traceback（`sys.excepthook` 抓不到）
- terminal 里看不到任何错误信息
- 进程"安静"地消失
- 反过来，**没有 dialog 打开时，按 Caps Lock 不崩**——所以早期容易误以为没问题

## 怎么诊断到根因

Python 进程被信号杀死时，macOS 会在 `~/Library/Logs/DiagnosticReports/` 写一份 `.ips` 崩溃报告。打开最新一份，关键调用栈是：

```
faulting thread (pynput's CGEventTap callback thread):
  m_CGEventTapCallBack                           ← pynput 的事件回调
  → [NSEvent eventWithCGEvent:]
    → CreateEventWithCGEvent
      → TSMSetCapsLockKeyTransitionDetected      ← TSM 处理 Caps Lock
        → TSMAdjustCapsLockPressAndHold
          → ProcessCapsLockSequenceKeyUp
            → TISIsDesignatedRomanModeCapsLockSwitchAllowed
              → TSMGetInputSourceProperty
                → islGetInputSourceListWithAdditions
                  → dispatch_assert_queue        ← SIGTRAP 在这里
```

异常信息：

```
"exception":{"codes":"...","type":"EXC_BREAKPOINT","signal":"SIGTRAP"}
"termination":{"indicator":"Trace/BPT trap: 5","byProc":"exc handler"}
```

这是 libdispatch 的"严格队列断言"：调用方声明了"我必须在 X 队列（通常是主线程的 dispatch queue）上跑"，runtime 检测到当前不在那个队列上，直接 abort 进程。

## 为什么是 pynput 的锅

pynput 在 macOS 上的键盘监听实现长这样：

```python
# 简化版（实际见 pynput/_darwin.py）
tap = Quartz.CGEventTapCreate(
    Quartz.kCGSessionEventTap,
    Quartz.kCGHeadInsertEventTap,
    Quartz.kCGEventTapOptionDefault,
    Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | ...,
    self._handler,                  # ← 我们的回调
    None,
)
# ...在一个新线程里跑 CFRunLoop 来 service 这个 tap
```

每次按键，macOS 把事件投递到这个**后台线程上的 CFRunLoop**，pynput 的 handler 在那里被调用。在 handler 里，pynput 顺手调用了：

```python
ns_event = NSEvent.eventWithCGEvent_(cg_event)
```

**`NSEvent.eventWithCGEvent:` 不是 thread-safe 的**。它内部会查 TSM（输入法系统）来给 NSEvent 填充字段，而 TSM 的多个 API 要求只能在主线程调用。这个 API 调用没有任何编译期 / 静态检查能挡住，所以 pynput 这么用了很多年也"能跑"。

直到 macOS 在某个版本（应该是 Sonoma 之后）给 libdispatch 加了那个严格断言。

## 为什么不是每次按 Caps Lock 都崩

崩溃不是确定的，是 race。原因有两层：

### 第一层：TSM 在每个进程里是"按需初始化"的

如果 MaxVoice 进程里**从来没有任何 Cocoa text input client 被激活**，TSM 在这个进程里处于"未初始化"状态。pynput 的回调里那串 TSM 调用在这种状态下基本上是 no-op，断言走不到。

但是——

### 第二层：打开任何 Qt dialog 都会唤醒 TSM

Qt 把 dialog 推到前台、设为 key window，会让 macOS 在我们进程里**初始化 Cocoa 文本输入相关的子系统，包括 TSM**。哪怕 dialog 里没有 `QLineEdit`、`QTableWidget` 这种可编辑控件（History dialog 就是只读的），光是窗口聚焦就够了。

**TSM 一旦被唤醒**，pynput 后台线程上那段调用就**真的会走完**——立刻踩到 `dispatch_assert_queue`，进程秒杀。

### 加起来的 user-visible 行为

| 场景 | TSM 状态 | 按 Caps Lock |
|---|---|---|
| MaxVoice 启动后什么 dialog 都没开 | 未唤醒 | 不崩 |
| 打开 Settings / History / Dictionary | 唤醒 | **必崩** |
| 关掉 dialog 后过几秒 | 仍然唤醒（不会自动 sleep） | **仍崩**（一直到进程退出） |

跟输入法是不是中文**无关**——TSM 唤醒后，任何输入源都会触发那段 Caps Lock 检查。中文 IME 只是让普通使用中更容易碰 Caps Lock，不是触发条件。

## 为什么之前没人发现

这个雷自打 `d216444 first version` 就在那里。之所以"之前没崩"，纯粹是因为：

1. 没人按过 Caps Lock。Caps Lock 在日常打字里出现频率极低。
2. 真按过的时候碰巧 dialog 没开。
3. 早期使用主要是录音，没怎么开过 Settings。

加了 Dictionary 功能之后，用户开始花更多时间在配置 dialog 里（要打字加词条），第一次撞上"dialog 开 + 按 Caps Lock"的组合，雷就引爆了。**Dictionary 本身没有任何 bug，它只是把潜伏的雷暴露出来了。**

## 失败的尝试：pause/resume

第一次想到的"快速止血"方案是：dialog 打开时把 pynput listener 停掉，关 dialog 再启动。

```python
def open_settings():
    app.hotkey.pause()   # listener.stop()
    try:
        dlg.exec()
    finally:
        app.hotkey.resume()  # listener.start()
```

**这个方案直接撞到了 pynput 的另一个雷**，而且这个雷的注释就在 `hotkey.py` 我自己面前：

```python
def update(self, hotkeys: dict[str, str]) -> None:
    # Restarting the pynput listener tears down + reinstalls a CGEventTap on
    # macOS, which races with Qt's event loop and crashes the process. Skip
    # the restart when the combos haven't actually changed.
```

`pynput.stop() → start()` 会拆掉 `CGEventTap` 再装一个，这个过程跟 Qt 的 event loop 抢 NSRunLoop 资源，又是一种 race，又是直接崩。

结果：原本"按 Caps Lock 崩"变成"关 dialog 崩"，按下葫芦浮起瓢。问题在于**只要还在用 pynput，就在踩雷之间反复横跳**。

## 真正的修复：换成 NSEvent monitor

`src/maxvoice/hotkey.py` 整个换成 PyObjC 的 NSEvent 监听：

```python
from AppKit import NSEvent, NSEventMaskKeyDown, ...

self._global_token = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
    NSEventMaskKeyDown, self._global_handler
)
self._local_token = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
    NSEventMaskKeyDown, self._local_handler
)
```

为什么 NSEvent monitor 同时解决两个问题：

1. **Apple 保证 monitor 的 handler 在主线程上调用。**  Caps Lock 触发的那段 TSM 调用现在跑在主线程，断言天然满足。
2. **`addGlobalMonitor… / removeMonitor:` 都是主线程操作，跟 Qt 的 event loop 共用 NSRunLoop。**没有 stop/start race。

副作用是个 bonus：dialog 打开时按热键也能正常工作（pynput 时代要么崩、要么我们故意 pause）。

### Public API 不变

`HotkeyListener` 的对外接口（`__init__`、`start`、`stop`、`update`、`on_toggle` 回调）跟 pynput 版本字节级一致。所以 `app.py`、`gui/hotkey_edit.py`、配置文件里的 `<ctrl>+<alt>+q` 字符串格式全部不用动。

### 实现里要小心的细节

| 细节 | 不处理会怎样 |
|---|---|
| Mask 掉 `NSEventModifierFlagCapsLock` | Caps Lock 开/关时同一个组合会被认为是不同的，热键时灵时不灵 |
| 跳过 `event.isARepeat()` | 长按热键会反复 toggle，录音被开开关关 |
| Global 和 Local 两个 monitor 都要装 | 只装 global，自己窗口聚焦时收不到；只装 local，别的 app 聚焦时收不到 |
| `addGlobalMonitor…` 返回 `nil` 时打 warning | Accessibility 权限缺失会静默失败，用户以为热键坏了 |
| 用 keycode 匹配 F 键、用字符匹配字母 | `charactersIgnoringModifiers()` 给 F 键返回的是奇怪 Unicode |

### Local monitor 必须返回 event

```python
def _local_handler(self, event):
    mode = self._match(event)
    if mode:
        self._fire(mode)
    return event   # ← 不返回的话事件被吞，焦点 widget 收不到键
```

返回 `None` 会"吞掉"这个键，焦点上的 widget 就收不到输入了。我们只想旁听，不想拦截，必须 `return event`。

Global monitor 没法吞事件，签名是 `(NSEvent) -> None`——这是 Apple 的限制，不是我们能改的。意思是：当 MaxVoice 在后台、用户在别的 app 里按 `Ctrl+Alt+Q`，那个 app 也会收到这个键。pynput 之前其实也是类似行为，没人觉得这是问题。

## 给未来自己的提醒

1. **macOS 上不要用基于后台线程 `CGEventTap` 的全局键盘库。** pynput、`keyboard` (PyPI 上那个)、`pyHook`、几乎所有"跨平台 keyboard hook"库在 macOS 上都是这种实现。新版 macOS 的严格断言让它们随时可能炸。
2. **macOS 全局键盘的正确姿势是 `NSEvent.addGlobalMonitorFor…`**（PyObjC AppKit）或者更底层的 `RegisterEventHotKey`（Carbon API）。两者都在主线程跑。
3. **看到 "Trace/BPT trap: 5" + 没有 Python traceback，先去 `~/Library/Logs/DiagnosticReports/` 找 `.ips` 文件。** Python 层抓不到的崩溃几乎都在那里有线索。
4. **当一段代码自带"千万别 X，会跟 Y race 崩"的注释时，认真读这条注释。** 我加 pause/resume 的时候没仔细读 `update()` 上方那段警告，结果重蹈覆辙。注释写在那里就是为了这种情况。
5. **"修复" race 类崩溃时，先想清楚根因，不要绕。** pynput 的所有问题都来自"在错的线程上调 TSM"这一个根因。任何不解决根因的方案（pause/resume、try/except、避免按某些键）都只是在挪雷，不是在拆雷。

## 相关文件 / 引用

- 当前实现：`src/maxvoice/hotkey.py`
- 调用方（无需修改）：`src/maxvoice/app.py`
- 热键配置 GUI（无需修改）：`src/maxvoice/gui/hotkey_edit.py`
- pynput 的 macOS 实现：[pynput/_darwin.py](https://github.com/moses-palmer/pynput/blob/master/lib/pynput/keyboard/_darwin.py)
- Apple 文档：[NSEvent.addGlobalMonitorForEventsMatchingMask:handler:](https://developer.apple.com/documentation/appkit/nsevent/1535472-addglobalmonitorforeventsmatchin)
- libdispatch 严格断言背景：搜 "dispatch_assert_queue" + "EXC_BREAKPOINT"
