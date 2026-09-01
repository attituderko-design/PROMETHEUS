# FULGUR I v8 組立・初通電チェックリスト

対象は **Wireless-Tag WT32-ETH01 + EIC-801 + SN74AHCT125N + PL9823-F8 ×6** です。

> `FULGUR_circuit_schematic.*` / `FULGUR_wiring_guide.*` は旧ESP32-POE版のため使用禁止です。穴位置・配線は統合BOM/設計図 v8 を正とします。

## 0. 固定構成

- 制御/Ethernet: WT32-ETH01
- ブレッドボード: EIC-801 1枚
- LED data: GPIO4
- SAFE/ARM: GPIO14 + 外付け10kΩ pulldown
- 電源: 5V/2A ACアダプター -> MJ-10H -> CW-SB11KKFF -> +5V BUS
- PL9823-F8: ケース面6灯
- 0.1µF: PL9823各1個 + SN74 1個 = 7個使用
- ケース配線: 24AWG撚り線4色
- 書込み: AE-FT234X + Micro-B USBケーブル
- FULGUR IP: `2.0.0.10`
- Art-Net: Universe 0 / ch 1–18

## 1. WT32の実装

- [ ] 標準WT32-ETH01・左右13pinであることを確認。
- [ ] 1×40ピンヘッダから13pinを2本作る。
- [ ] WT32左右列へ平行にはんだ付けする。
- [ ] EIC-801の左列 `B1:B13`、右列 `I1:I13` へ挿す。
- [ ] RJ45側をrow1側、ブレッドボード上端外へ向ける。
- [ ] `B～I / rows1–17` はWT32占有範囲として他部品を置かない。
- [ ] `A/J / rows1–17` は低背24AWG線以外を置かない。

WT32装着前に次の低背線を施工します。

| 信号 | 始点 | 終点 |
|---|---|---|
| GND | A1 | B22 |
| GPIO4 | A3 | A25 |
| GPIO14 | A6 | R+2 |
| +5V | J2 | B23 |
| 3.3V | J4 | L+2 |

## 2. 電源BUS

- [ ] row22をGND BUSにする。
- [ ] row23を+5V BUSにする。
- [ ] E22-F22でGNDを左右接続。
- [ ] E23-F23で+5Vを左右接続。
- [ ] MJ-10H中心端子 -> CW-SB11KKFF -> +5V BUS。
- [ ] MJ-10H GND -> GND BUS。
- [ ] 電源OFFで+5V BUSとGND BUSが短絡していないことをテスターで確認。
- [ ] ACアダプター単体がセンタープラス約5Vであることを確認。

## 3. SN74AHCT125N

- [ ] `E24:E30 / F24:F30` に中央溝を跨いで配置。ノッチ側=row24。
- [ ] pin14 VCC -> +5V。
- [ ] pin7 GND -> GND。
- [ ] pin1 /1OE -> GND。
- [ ] pin2 1A <- GPIO4。
- [ ] pin3 1Y -> R0 75Ω -> LED1 DIN。
- [ ] 未使用入力/OEは統合配線一覧どおりGNDへ固定し、浮かせない。
- [ ] 0.1µFをH24-H25へ配置。

## 4. SAFE / ARM

- [ ] WT32 3.3V -> ASW +端子。
- [ ] ASW switched-output -> GPIO14。
- [ ] ASW GND -> GND。
- [ ] GPIO14 -> 10kΩ -> GND。
- [ ] GPIO14へ5Vがつながっていないことを確認。

## 5. PL9823ケースハーネス

各LEDはケース面へ取り付け、4脚から24AWG撚り線を独立してEIC-801へ戻します。

色ルール:

- pin1 GND = 黒
- pin2 DOUT = 青
- pin3 VDD +5V = 赤
- pin4 DIN = 黄

各LEDのpin1-pin3間へ0.1µFをLED直近ではんだ付けします。

| LED | GND | DOUT | VDD | DIN |
|---|---|---|---|---|
| #1 | L-8 | L-15 | L+8 | L+15 |
| #2 | L-9 | L-21 | L+9 | L+21 |
| #3 | L-10 | L-27 | L+10 | L+27 |
| #4 | R-8 | R-15 | R+8 | R+15 |
| #5 | R-9 | R-21 | R+9 | R+21 |
| #6 | R-10 | R-27 | R+10 | R+27 |

データ順:

`SN74 -> R0 -> #1 -> R1 -> #2 -> R2 -> #3 -> R3 -> #4 -> R4 -> #5 -> R5 -> #6`

#6 DOUTは未接続です。

75Ω配置:

- R0: D26-D20
- R1: L-18-L+20
- R2: L-24-L+26
- R3: E21-F21
- R4: R-18-R+20
- R5: R-24-R+26

## 6. 初通電前

- [ ] +5V BUS-GND BUSが短絡していない。
- [ ] GPIO4がSN74 pin2へ導通し、5V/GNDと短絡していない。
- [ ] GPIO14がASW出力と10kΩへ導通し、5Vと短絡していない。
- [ ] SN74 pin14=5V / pin7=GND。
- [ ] WT32装着方向がRJ45=row1外向き。
- [ ] LEDはまだ1灯だけ、または全LEDを外した状態で最初の電源確認を行う。

## 7. 初通電

1. 主電源ON。
2. GND基準で+5V BUSが約5Vであることを測る。
3. WT32 3.3Vが約3.3Vであることを測る。
4. 異臭・煙・異常発熱があれば即OFF。
5. 問題なければ電源OFF。

## 8. FULGURファーム書込み

AE-FT234X:

```text
TXD -> WT32 RX0
RXD -> WT32 TX0
GND -> WT32 GND
```

1. 主電源OFF。
2. IO0-GNDを接続してWT32をdownload modeへ入れる。
3. `./scripts/flash_fulgur_pixel.ps1 COMx` を実行。
4. 書込み完了後IO0-GNDを外す。
5. WT32を再起動する。

Serial Monitorで次を確認:

- `FULGUR`
- `Wireless-Tag WT32-ETH01`
- IP `2.0.0.10`
- SAFE/ARM GPIO `14`
- preview GPIO `4`

## 9. 1灯 -> 6灯試験

- [ ] LED #1だけでArt-Net ch1–3を確認。
- [ ] 電源OFFで#2を追加、ch4–6を確認。
- [ ] 同様に#6まで追加。
- [ ] 6灯がch1–18へ正しく対応。
- [ ] FULGURは受信色へ即時切替。
- [ ] SAFE中もプレビューはLIVE。
- [ ] LAN抜線でプレビューBLACK。
- [ ] Art-Net 1500ms timeoutでプレビューBLACK。
- [ ] ARM位置起動ではDMX LOCKED SAFE。
- [ ] SAFEを一度通過してからARMにした場合だけ将来DMXを許可。

## 10. 完成判定

`fulgur_pixel` の完成条件:

- WT32-ETH01でビルド/書込み成功。
- Ethernet link正常。
- `2.0.0.10`でArt-Net受信。
- PL9823×6がch1–18へ対応。
- SAFE/ARM、LAN断、timeoutのフェイルセーフ動作が仕様どおり。
- ケース内で露出導体の短絡がなく、ハーネスの引張荷重がLED脚へ直接掛からない。

> 現在の卓上試作 `fulgur_pixel` はローカルプレビューのみです。物理DMXにはRS-485ドライバ回路が別途必要です。
