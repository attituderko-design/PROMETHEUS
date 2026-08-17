# FULGUR v3 組立・初通電チェックリスト

対象は **Olimex ESP32-POE（非ISO）+ SN74AHCT125N + PL9823-F8 × 6** です。回路は `FULGUR_circuit_schematic.svg`、見ながら組む図は `FULGUR_wiring_guide.svg` を参照してください。

## この版の電源方式

- 5V/2A ACアダプターを唯一の電源にする。
- RJ45はデータ通信専用。PoE給電されたLANへ接続しない。
- 主電源ON中は、Micro-USB・PoE・LiPoを接続しない。
- ファームウェア書込み時は主電源をOFFにし、PoE-LANとLiPoを外してからMicro-USBを接続する。

## 0. はんだ付け前

- [ ] ACアダプター、LAN、USB、LiPoを全部外す。
- [ ] PL9823のpin 1をデータシートで確認する。足の長さや線色だけで決めない。
- [ ] SN74AHCT125Nの切欠きとpin 1位置を確認する。
- [ ] USBケーブルから取り出した4本は、テスターの導通モードで両端を照合してラベルを付ける。
- [ ] 同じケーブル内の別の線同士が導通しないことを確認する。

推奨ラベルは `赤=+5V`、`黒=GND`、`白=DIN`、`緑=DOUT` です。ただし元のUSBケーブル色は信用せず、測定後に役割を決めます。

## 1. 電源だけを作る

- [ ] DCジャック中心端子 → 主電源スイッチ → +5V_BUS。
- [ ] DCジャック外周端子 → GND_BUS。
- [ ] 主電源スイッチはプラス側だけを切る。
- [ ] 電源OFFのまま、+5V_BUSとGND_BUSが短絡していないことを確認する。
- [ ] ACアダプター単体の中心がプラス、約5Vであることを電圧モードで確認する。

## 2. ESP32とレベル変換IC

- [ ] ESP32 `+5V` → +5V_BUS。
- [ ] ESP32 `GND` → GND_BUS。
- [ ] ESP32 `GPIO4` → SN74AHCT125N pin 2（1A）。
- [ ] SN74 pin 1（/1OE）→ GND。
- [ ] SN74 pin 3（1Y）→ R0 75Ω → LED1 pin 4（DIN）。
- [ ] SN74 pin 14（VCC）→ +5V_BUS。
- [ ] SN74 pin 7（GND）→ GND_BUS。
- [ ] C1 0.1µFをSN74 pin 14–pin 7のすぐ近くへ接続する。
- [ ] 未使用入力は、pin 4+5、pin 10+9、pin 13+12をそれぞれGNDへ接続する。
- [ ] 未使用出力pin 6、8、11は未接続にする。

ICソケットを使う場合は、まずソケットだけをはんだ付けします。IC本体は電源確認後に挿します。

## 3. SAFE / ARMスイッチ

- [ ] ESP32 `3.3V` → ASW-07Dの＋端子。
- [ ] ASW-07Dのswitched-output端子 → ESP32 `GPIO14`。
- [ ] ASW-07DのLED/GND端子 → GND。
- [ ] GPIO14 → 10kΩ → GND（プルダウン）。
- [ ] GPIO14へ5Vがつながっていないことを確認する。

## 4. PL9823を最初は1灯だけ接続

- [ ] LED1 pin 1（GND）→ GND_BUS。
- [ ] LED1 pin 3（VDD）→ +5V_BUS。
- [ ] C2 0.1µFをLED1 pin 1–pin 3のすぐ近くへ接続する。
- [ ] SN74 pin 3 → R0 75Ω → LED1 pin 4（DIN）。
- [ ] LED1 pin 2（DOUT）は、1灯試験中は未接続にする。
- [ ] 露出したはんだ部は熱収縮チューブで絶縁する。グルーは絶縁後の固定補助に使う。

## 5. 通電前テスター確認

すべての電源を外し、ICソケットを使った場合はICをまだ挿さずに確認します。

- [ ] +5V_BUS–GND_BUSが短絡していない。
- [ ] +5V_BUSがESP32 +5V、SN74 pin 14、LED1 pin 3へだけ導通する。
- [ ] GND_BUSがESP32 GND、SN74 pin 1/7、LED1 pin 1へ導通する。
- [ ] GPIO4がSN74 pin 2へ導通し、+5V/GNDとは短絡していない。
- [ ] SN74 pin 3からR0を通り、LED1 pin 4へ導通する。
- [ ] GPIO14がスイッチ出力と10kΩへ導通し、+5Vとは短絡していない。

## 6. 初通電

1. ESP32、SN74、LED1の向きをもう一度確認する。
2. 主電源をONにする。
3. GND基準で、+5V_BUSが約5V、ESP32 3.3Vが約3.3Vであることを測る。
4. 異臭、煙、急な発熱があればすぐOFFにする。
5. ファームウェアとArt-Netを使ってLED1を確認する。
6. SAFE/ARMを切り替え、Serial MonitorでGPIO14の状態を確認する。

LEDが点かないときは、電源を切って `DIN/DOUTの逆`、`LEDのpin番号`、`GND共通`、`SN74の切欠き方向` の順に見直します。

## 7. 6灯へ増やす

1灯が成功してから、電源OFFで1灯ずつ追加します。

| 追加 | 接続 |
|---|---|
| LED2 | LED1 pin 2（DOUT）→ R1 75Ω → LED2 pin 4（DIN） |
| LED3 | LED2 pin 2（DOUT）→ R2 75Ω → LED3 pin 4（DIN） |
| LED4 | LED3 pin 2（DOUT）→ R3 75Ω → LED4 pin 4（DIN） |
| LED5 | LED4 pin 2（DOUT）→ R4 75Ω → LED5 pin 4（DIN） |
| LED6 | LED5 pin 2（DOUT）→ R5 75Ω → LED6 pin 4（DIN） |

各LEDのpin 1をGND、pin 3を+5Vへ接続し、pin 1–pin 3間に0.1µFを1個ずつ追加します。LED6 pin 2（DOUT）は未接続です。

## 8. 完成判定

- [ ] 6灯がFULGURのArt-Net channel 1–18に対応する。
- [ ] FULGURは受信色へ即時に切り替わる。
- [ ] SAFEでもローカルプレビューは見える。
- [ ] Ethernet断またはArt-Netタイムアウトで6灯が消える。
- [ ] ARM位置で起動してもDMXはLOCKED SAFEのまま。
- [ ] SAFEを一度通過してからARMにしたときだけ、将来のDMX出力が許可される。

> 現在の卓上試作 `fulgur_pixel` はローカルプレビューのみです。XLRへESP32のGPIOを直結してはいけません。物理DMXにはRS-485ドライバ回路が別途必要です。
