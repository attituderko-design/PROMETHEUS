# PROMETHEUS — Scriabin Luce Controller v0.6.3

PROMETHEUS is one product repository. The Windows controller and the FULGUR/AURORA node firmware are separate deployable components of that product, not separate services.

## Repository layout

- Root Python files: Windows controller and `PROMETHEUS.exe` build.
- `firmware/`: FULGUR/AURORA WT32-ETH01 firmware, hardware documents and flashing scripts.
- `.github/workflows/test.yml`: controller tests.
- `.github/workflows/firmware-build.yml`: all four PlatformIO firmware builds.

The former `PROMETHEUS_NODE_FIRMWARE` history is retained in this repository through the firmware integration merge.

## 正式コードネーム

- Windows executable: **`PROMETHEUS.exe`**
- Test Luce 1 node: **FULGUR**
- Test Luce 2 node: **AURORA**

実行ファイル名も正式コードネームに合わせて **`PROMETHEUS.exe`** とします。

## v0.6.3の主変更

### 本番安全性と通信安定性

- Art-Net出力OFF時に3回のBLACKOUTフレームを即時送信
- 定期送信を900msから200msへ短縮
- FULGUR/AURORAを個別送信し、一方の異常で他方を止めない
- IPアドレスとUniverseを保存前・送信前に検証
- アプリがフォーカスを失った際にPCキーボード由来の音を解除
- MIDI入力異常時にデバイスハンドルを確実に閉じる
- ログを1MB×最大4世代にローテーション

### PCキーボード入力

起動直後からPCキーボード入力が有効になるよう、初期フォーカス処理を修正しています。MIDI機器が無い場合の出力テスト／フォールバックにも使用できます。

MIDIキーボードが接続されていなくても、ラップトップ本体のキーボードだけで Luce 1 / Luce 2 を演奏できます。
マウスによる88鍵表示クリックとは異なり、PC Keyboard Performance Input は正式な演奏入力です。

デフォルト配列:

```text
Luce 1 / FULGUR
C   C#  D   D#  E   F   F#  G   G#  A   A#  B
Q   2   W   3   E   R   5   T   6   Y   7   U

Luce 2 / AURORA
C   C#  D   D#  E   F   F#  G   G#  A   A#  B
Z   S   X   D   C   V   G   B   H   N   J   M
```

- 各バンクは C4-B4 としてGUI上に表示
- Luceの色決定は pitch class なので色制御上は1オクターブで全12色を演奏可能
- MIDIとPCキーボードは同時使用可能
- 同じ音をMIDIとPCキーボードが同時に保持しても、一方のNote Offだけでは消灯しない
- MIDIを切断してもPCキーボード入力は残る
- OSのキーリピートは二重Note Onとして扱わない
- IP等のテキスト入力欄へ文字入力中は演奏キーを発火させない

注意: PC本体キーボードの物理的なkey rollover / ghosting性能は機種依存です。3音和音を本番フォールバックとして使う場合は、実機で必要なキー組合せを事前確認してください。

### Luce 1 / Luce 2 のArt-Net送信先を分離

試作・本番設計に合わせて、Luce 1 と Luce 2 は別IPへユニキャストできます。

```text
PROMETHEUS
  ├─ Art-Net → FULGUR IP
  └─ Art-Net → AURORA IP
```

デフォルト:

- FULGUR: `2.0.0.10`, Universe 0
- AURORA: `2.0.0.11`, Universe 0

現在は両ノードへ同じ12-output ArtDmx frameを送り、
FULGUR側はlogical outputs 1-6、AURORA側は7-12を使用する構成です。

## Luceロジック

各Luce最大3音を6出力へ循環配置します。

```text
1 note : A A A A A A
2 notes: A B A B A B
3 notes: A B C A B C
```

4音目以降はoverflowとして警告表示し、先に押された3音を出力対象として維持します。

## FINAL WHITE

1913 Parisian Score終盤の `becoming glaring, white` に対応する独立エフェクトです。

- GUI slider 0-100%
- F12で0/100%
- Luce 1 / Luce 2 全出力へ適用

## 配布

通常利用者へ渡すのは1ファイルです。

```text
PROMETHEUS.exe
```

Python / pygame / config.json をexe横へ置く必要はありません。
設定変更時にはWindowsが以下を使用します。

```text
%APPDATA%\ScriabinLuce\config.json
%APPDATA%\ScriabinLuce\luce.log
```

## Windowsビルド

PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_release.ps1
```

生成物:

```text
dist\PROMETHEUS.exe
```

## テスト

```powershell
py -m unittest discover -s tests -v
```

v0.6.3作成時点でcore/app logic tests 17件合格。


## v0.6.2 keyboard input fix
- Laptop keyboard gets neutral focus on startup.
- Readonly MIDI comboboxes no longer block performance keys.
- Windows virtual-key fallback added for Japanese IME/layout cases.
- Q/2/W/3/E/R/5/T/6/Y/7/U = FULGUR, Z/S/X/D/C/V/G/B/H/N/J/M = AURORA.
