# PROMETHEUS NODE FIRMWARE v0.3

PROMETHEUS用の**有線Art-Netノード**・ファームウェアです。

## 対応ノード

| コードネーム | 用途 | ハード |
|---|---|---|
| FULGUR | Luce 1 | Olimex ESP32-POE |
| AURORA | Luce 2 | Wireless-Tag WT32-ETH01 |

両方とも有線Ethernet専用です。Wi-Fiは使用しません。

## v0.3: SAFE中のローカル・プレビュー

PL9823-F8 x6 の役割を**ノード内蔵のローカル・プレビューモニター**として固定しました。

実運用は次の順序を想定します。

1. POWER ON
2. SAFEのまま起動
3. PROMETHEUSからArt-Netを送る
4. ケースを開け、PL9823-F8 x6で色・6出力・通信を確認
5. SAFE -> ARM
6. 初めてステージDMXをLIVEにする
7. 異常時はARM -> SAFEでDMXを即座に0へ戻す

### SAFE / ARM と出力の関係

| 状態 | PL9823ローカルプレビュー | ステージDMX |
|---|---|---|
| SAFE + Ethernet/Art-Net正常 | 表示する | 全ch 0 |
| ARM + Ethernet/Art-Net正常 | 表示する | LIVE |
| Ethernet断 | 消灯 | 全ch 0 |
| Art-Net 1500ms timeout | 消灯 | 全ch 0 |
| ARM位置のまま起動 | 表示可能 | LOCKED SAFE / 全ch 0 |

重要なのは、**SAFEはローカルプレビューを禁止しません。SAFEが禁止するのはステージDMXです。**

したがって、舞台照明を発光させずに

`PROMETHEUS -> Ethernet -> Art-Net -> FULGUR/AURORA -> 色変換 -> 6出力`

までを目視確認できます。

## SAFE / ARM インターロック

GPIO14をSAFE/ARM入力として両ノードで共通化しています。

1. 電源投入直後のDMXは必ずSAFE。
2. ARM位置のまま電源を入れてもDMXはLIVEにならない。
3. 起動後に一度SAFEを安定して検出する必要がある。
4. その後のSAFE->ARM遷移で初めてDMX出力を許可する。
5. ARM->SAFEは即座にDMXゲートを閉じる。
6. ARM中でもEthernet link断または有効なArt-Netが1500ms以上来なければDMXは0。
7. DMX modeではSAFE時にもDMX信号自体は止めず、512スロット=0を連続送出する。

ステージDMXのLIVE条件は:

`ARM authorized AND Ethernet link UP AND fresh valid Art-Net`

ローカルプレビュー条件は:

`Ethernet link UP AND fresh valid Art-Net`

です。

### FULGURの107058赤ミサイルスイッチ

試作ではスイッチを**3.3V系**で使います。

```text
107058 +端子               -> ESP32 3.3V
107058 LED/GND端子         -> GND
107058 switched-output端子 -> GPIO14
GPIO14                     -> 10kΩ -> GND
```

赤LEDには560Ωが内蔵されています。GPIO14へ5Vを入れない構成です。

## 現在のPL9823プレビュー構成

PROMETHEUS v0.6.2 は両ノードへ同じArtDmxフレームを送ります。

- FULGUR: `2.0.0.10`, Universe 0
- AURORA: `2.0.0.11`, Universe 0
- FULGURはArt-Net channel 1～18をPL9823-F8 x6へ表示
- AURORAはArt-Net channel 19～36をPL9823-F8 x6へ表示

信号経路:

`ESP32 GPIO4 -> SN74AHCT125N -> PL9823-F8 x6`

この回路は将来DMX出力を追加した後も**ローカルプレビューとして残す**前提です。

## DMX構成

DMX buildでは、PL9823プレビューを動かしたまま、受信Universe全体を物理DMX512へ出力します。

`ESP32 UART -> RS-485 driver -> DMX OUT -> stage fixtures`

予約ピン:

- FULGUR: DMX TX = GPIO33, DE = GPIO32
- AURORA: DMX TX = GPIO17, DE = GPIO33

**RS-485ドライバ実装前にESP32 GPIOをDMX XLRへ直結してはいけません。**

## PlatformIO environments

```text
fulgur_pixel
  FULGUR / PL9823プレビューのみ（現在の卓上試作）

aurora_pixel
  AURORA / PL9823プレビューのみ（現在の卓上試作）

fulgur_dmx
  FULGUR / PL9823プレビュー + DMX512

aurora_dmx
  AURORA / PL9823プレビュー + DMX512
```

現在まず使用するのは:

```powershell
pio run -e fulgur_pixel
```

## FULGURへの書込み

```powershell
.\scripts\flash_fulgur_pixel.ps1 COM5
```

ESP32-POEはMicro-USB書込み器内蔵です。

## AURORAへの書込み

AE-FT234Xを使用します。

```text
AE-FT234X TXD -> WT32 RXD
AE-FT234X RXD -> WT32 TXD
AE-FT234X GND -> WT32 GND
```

書込み開始時はIO0をGNDへ落としてリセット/再投入し、完了後にIO0-GNDを外します。

```powershell
.\scripts\flash_aurora_pixel.ps1 COM6
```

## PC側の有線LAN設定

直結例:

```text
Windows Ethernet: 2.0.0.1 / 255.0.0.0
FULGUR:           2.0.0.10
AURORA:           2.0.0.11
Universe:         0
UDP:              6454
```

## 実機検証順序

到着後はFULGURから:

1. ファームウェアをビルド
2. ESP32-POEへ書込み
3. SAFE/ARMだけをSerial Monitorで確認
4. PL9823-F8を1灯で確認
5. 6灯へ拡張
6. SAFEのままPROMETHEUSからArt-Net送信し、6灯プレビューを確認
7. ARMへ切り替えてもプレビューが変化しないことを確認
8. LAN抜線 / Art-Net timeoutでプレビューが消灯することを確認
9. 将来DMX回路追加後、SAFE=DMX zero / ARM=DMX liveを確認

## 現時点の検証状態

v0.3はソース実装段階です。こちらには実機がないため、ESP32-POE / WT32-ETH01への物理書込み・点灯試験は未実施です。また、この作業環境にはPlatformIOがないため、v0.3のESP32向け実コンパイルも未実施です。

実機到着後の最初の作業は**FULGURのビルドと書込み**です。
