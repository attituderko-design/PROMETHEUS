# PROMETHEUS NODE FIRMWARE v0.3.3

PROMETHEUS用の**有線Art-Netノード**・ファームウェアです。

## 対応ノード

| コードネーム | 用途 | ハード | IP | Art-Net RGB |
|---|---|---|---|---|
| FULGUR | Luce 1 | Wireless-Tag WT32-ETH01 | `2.0.0.10` | ch 1–18 |
| AURORA | Luce 2 | Wireless-Tag WT32-ETH01 | `2.0.0.11` | ch 19–36 |

両方とも有線Ethernet専用です。Wi-Fiは使用しません。

## v0.3.3: FULGURをWT32-ETH01へ統一

- FULGURのハードをOlimex ESP32-POEからWT32-ETH01へ変更。
- FULGURの論理仕様は維持: GPIO4、GPIO14、IP `2.0.0.10`、Art-Net ch 1–18。
- `fulgur_pixel` / `fulgur_dmx` のPlatformIO boardを `wt32-eth01` に変更。
- FULGURの書込みをAE-FT234X + IO0=GNDのWT32手順へ変更。
- GitHub ActionsのPythonセットアップで誤って指定していたpip cacheを外し、PlatformIO buildが実行されるよう修正。

## ノード別の色遷移

- FULGURは受信色へ即時に切り替わります。
- AURORAはRGBを250msの線形フェードで切り替えます。
- 同じ色のArt-Net再送ではフェード時間をリセットしません。
- SAFE、LAN切断、Art-Netタイムアウト時のDMXゼロとプレビュー消灯は即時です。

## SAFE / ARM と出力

GPIO14をSAFE/ARM入力として両ノードで共通化しています。

1. 電源投入直後のDMXは必ずSAFE。
2. ARM位置のまま電源を入れてもDMXはLIVEにならない。
3. 起動後に一度SAFEを安定して検出する必要がある。
4. その後のSAFE->ARM遷移で初めてDMX出力を許可する。
5. ARM->SAFEは即座にDMXゲートを閉じる。
6. ARM中でもEthernet link断または有効なArt-Netが1500ms以上来なければDMXは0。
7. DMX modeではSAFE時にもDMX信号自体は止めず、512スロット=0を連続送出する。

| 状態 | PL9823ローカルプレビュー | ステージDMX |
|---|---|---|
| SAFE + Ethernet/Art-Net正常 | LIVE | 全ch 0 |
| ARM + Ethernet/Art-Net正常 | LIVE | LIVE |
| Ethernet断 | BLACK | 全ch 0 |
| Art-Net 1500ms timeout | BLACK | 全ch 0 |
| ARM位置のまま起動 | 表示可能 | LOCKED SAFE / 全ch 0 |

ステージDMXのLIVE条件:

`ARM authorized AND Ethernet link UP AND fresh valid Art-Net`

ローカルプレビュー条件:

`Ethernet link UP AND fresh valid Art-Net`

## SAFE/ARMハード

試作では107058赤ミサイルスイッチを**3.3V系**で使います。

```text
107058 +端子               -> WT32 3.3V
107058 LED/GND端子         -> GND
107058 switched-output端子 -> GPIO14
GPIO14                     -> 10kΩ -> GND
```

GPIO14へ5Vを入れません。

## PL9823ローカルプレビュー

PROMETHEUS v0.6.3 は両ノードへ同じArtDmxフレームを送ります。

- FULGUR: `2.0.0.10`, Universe 0, ch 1–18
- AURORA: `2.0.0.11`, Universe 0, ch 19–36

信号経路:

`WT32 GPIO4 -> SN74AHCT125N -> PL9823-F8 x6`

PL9823は将来DMX出力を追加した後もローカルプレビューとして残します。

## DMX構成

DMX buildではPL9823プレビューを動かしたまま、受信Universe全体を物理DMX512へ出力します。

`WT32 UART -> RS-485 driver -> DMX OUT -> stage fixtures`

予約ピン:

- FULGUR: DMX TX = GPIO33, DE = GPIO32
- AURORA: DMX TX = GPIO17, DE = GPIO33

**RS-485ドライバ実装前にGPIOをDMX XLRへ直結してはいけません。**

## PlatformIO environments

```text
fulgur_pixel
  WT32-ETH01 / FULGUR / PL9823プレビューのみ

aurora_pixel
  WT32-ETH01 / AURORA / PL9823プレビューのみ

fulgur_dmx
  WT32-ETH01 / FULGUR / PL9823プレビュー + DMX512

aurora_dmx
  WT32-ETH01 / AURORA / PL9823プレビュー + DMX512
```

FULGUR卓上試作のビルド:

```powershell
pio run -e fulgur_pixel
```

## WT32への書込み

FULGUR/AURORAともAE-FT234Xを使用します。

```text
AE-FT234X TXD -> WT32 RX0
AE-FT234X RXD -> WT32 TX0
AE-FT234X GND -> WT32 GND
```

書込み開始時はIO0をGNDへ落としてリセット/再投入し、完了後にIO0-GNDを外します。

FULGUR:

```powershell
.\scripts\flash_fulgur_pixel.ps1 COM5
```

AURORA:

```powershell
.\scripts\flash_aurora_pixel.ps1 COM6
```

## PC側の有線LAN設定

```text
Windows Ethernet: 2.0.0.1 / 255.0.0.0
FULGUR:           2.0.0.10
AURORA:           2.0.0.11
Universe:         0
UDP:              6454
```

PROMETHEUS PC側は、FULGURの物理基板変更に伴う設定変更を必要としません。

## 実機検証順序

1. `fulgur_pixel` をビルド。
2. AE-FT234XでWT32-ETH01へ書込み。
3. IO0-GNDを外して再起動。
4. Serial Monitorで `FULGUR`, `Wireless-Tag WT32-ETH01`, `2.0.0.10` を確認。
5. Ethernet linkを確認。
6. SAFE/ARM入力を確認。
7. PL9823-F8を1灯で確認。
8. 6灯へ拡張。
9. SAFEのままPROMETHEUSからArt-Net送信し、ch 1–18の6灯プレビューを確認。
10. LAN抜線 / Art-Net timeoutでプレビューが消灯することを確認。
11. 将来DMX回路追加後、SAFE=DMX zero / ARM=DMX liveを確認。

## 検証状態

- ソースロジック: v0.3.3へ更新済み。
- PlatformIO board: FULGUR/AURORAとも `wt32-eth01`。
- CI: `.github/workflows/build.yml` で4環境をビルドする。
- 実機書込み・点灯・Ethernet確認はWT32実機到着後に実施する。

FULGURの物理配線は `docs/FULGUR/FULGUR_build_checklist.md` と別管理の統合BOM/設計図を正とします。旧ESP32-POE用画像資料は参照禁止です。
