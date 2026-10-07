# Incipio CommandKit Metering

A Home Assistant custom integration that reads voltage, current and power from an Incipio CommandKit **CMNDKT-004**, using its existing HomeKit Device connection.

讓已經配對到 Home Assistant 的 Incipio CommandKit CMNDKT-004 顯示電壓、電流與功率。預設每 **10 秒**更新，可在新增整合時選擇 5 秒。

**0.1.0 為初版：11 個離線測試通過，尚未完成 HAOS 實機驗證。** 原始碼介面以 Home Assistant Core **2026.9.4**、aiohomekit **4.0.1** 為依據；更高版本仍需確認相容性。這是社群自訂整合，與 Incipio、CviLux 或 Opro9 沒有官方關係。

## 使用前

插座必須已經透過 **HomeKit Device / homekit_controller** 配對到 HA，而且開關可以正常控制。本整合直接使用該連線，不需再輸入 HomeKit PIN，也不需填寫 IP、HA token 或 MQTT 設定。

## 安裝方式一：HACS 自訂 repository

此方式需要已安裝 HACS，且本 repository 必須為 **public**。私人 repository 請用下面的手動安裝。

1. 在 HA 開啟 **HACS**，右上角 **⋮ → Custom repositories／自訂儲存庫**。
2. 輸入 `https://github.com/lee98064/ha-incipio-commandkit`，類型選 **Integration／整合**，按新增。
3. 搜尋 **Incipio CommandKit Metering**，開啟後按 **Download／下載**。
4. **重新啟動 Home Assistant Core**，再依下方「新增與使用」設定。

本專案可透過 HACS 的自訂 repository 安裝，尚未申請加入 HACS 預設清單。安裝動作與新增 HA 整合是兩個步驟。

HACS 操作依據：[官方自訂 repository 文件](https://www.hacs.xyz/docs/faq/custom_repositories/)與[下載說明](https://www.hacs.xyz/docs/use/repositories/dashboard/)。

## 安裝方式二：手動安裝

1. 到 [Releases](https://github.com/lee98064/ha-incipio-commandkit/releases/latest) 下載 **`incipio-commandkit-0.1.0.zip`**。
2. 解壓縮，把 `custom_components/incipio_commandkit/` 整個資料夾複製到 HA 的 **`/config/custom_components/incipio_commandkit/`**。可使用已設定的 Samba 分享或 File editor 等工具上傳。
3. 確認檔案直接位於該資料夾，避免多包一層：

   ```text
   /config/custom_components/incipio_commandkit/manifest.json
   /config/custom_components/incipio_commandkit/__init__.py
   /config/custom_components/incipio_commandkit/config_flow.py
   /config/custom_components/incipio_commandkit/coordinator.py
   /config/custom_components/incipio_commandkit/discovery.py
   /config/custom_components/incipio_commandkit/sensor.py
   /config/custom_components/incipio_commandkit/translations/
   /config/custom_components/incipio_commandkit/brand/
   ```

4. **重新啟動 Home Assistant Core**。這會短暫中斷 HA 控制，不需要重新配對插座。

也可以下載 GitHub **Code → Download ZIP**，從其中取出相同的 `custom_components/incipio_commandkit/`。

## 新增與使用

1. 等既有 **HomeKit Device** 整合載入。
2. 開啟 **設定 → 裝置與服務 → 新增整合**，搜尋 **Incipio CommandKit Metering**。
3. 選取你的 **CMNDKT-004**，更新間隔先選 **10 秒**。
4. 開啟插座裝置頁，會新增三個 sensor。也可到 **開發者工具 → 狀態**檢查：

   | 預設 entity ID | 資料 | 單位 | device_class |
   |---|---|---|---|
   | `sensor.incipio_voltage` | 電壓 | V | voltage |
   | `sensor.incipio_current` | 電流 | A | current |
   | `sensor.incipio_power` | 功率 | W | power |

   如果已有同名 entity，HA 可能加上尾碼；可以到 entity 設定中改名。

5. 在儀表板新增 **Entities／實體卡片**，選入這三個 sensor，就能查看數值。

原有 HomeKit Device 的插座開關會繼續使用。這三個 sensor 不需額外 YAML。

## 資料與限制

| 資料 | Characteristic UUID |
|---|---|
| Voltage | `032B12CF-D4E8-4277-9021-188816FD00C6` |
| Current | `08874E2E-5B63-4EEC-A146-4E2D93E5642A` |
| Power | `D7467855-8B65-42EC-98E1-496FF153F342` |

透過型號 `CMNDKT-004`、Energy Usage service UUID `14FA9D31-FC94-4F98-B00D-4AE878523748` 與三個可讀 characteristic UUID 找出 AID/IID，不把 13/14/15 寫死。

V / A / W 的對應依裝置 dump 的數值與值域推定，**尚無同型號原廠 UUID 對照表，也未用獨立電表驗證**。保留原始數值，不乘倍率或四捨五入。建議先比較負載開／關時的讀值。

功率 **W** 不是累計電量 **kWh**；本整合沒有建立可直接加入 Energy Dashboard 的累計電量 entity。

向既有 `HKDevice` 登記三個 pollable characteristic，呼叫原生 `async_update()`，沿用它的輪詢鎖、連線恢復和快取；原生已登記的其他可讀 characteristic 也可能一起被讀取。HomeKit 連線重新載入後會改用目前的連線和 metadata。短暫通訊失敗沿用原生可用性判斷，可能暫留上次數值。

本整合只提供電力監測，沒有韌體更新、LED 關閉或寫入 characteristic 的功能。它使用 HomeKit Device 的**內部 Python 介面**，Core 升級後需重新核對相容性。請勿同時安裝另一份讀取同一組 private UUID 的自訂整合，原生 pollable 登記集合沒有引用計數。

## 常見問題

**新增整合時找不到 CMNDKT-004**

先確認既有 HomeKit Device 整合已載入、插座開關仍可控制。只有型號完全符合 `CMNDKT-004` 且包含三個可讀 metering UUID 的裝置才會出現；FHH107 不在目前支援範圍。

**找不到整合名稱**

確認檔案位置是 `/config/custom_components/incipio_commandkit/manifest.json`，重新啟動 Core，再重新整理瀏覽器。查看 **設定 → 系統 → 日誌**中 `incipio_commandkit` 的錯誤。

**顯示 unavailable／unknown**

先檢查 HomeKit Device 是否可用。未載入、缺少服務或連線已確認不可用時會 unavailable；單項 HomeKit 錯誤或非法數值顯示 unknown。回報問題時附上 Core 版本與相關錯誤即可；不要上傳 HomeKit 配對私鑰或 HA token。

**如何調整更新間隔**

目前在新增時選擇 5 或 10 秒。要變更可刪除 **Incipio CommandKit Metering** 這筆整合，再重新新增；保留既有 **HomeKit Device** 整合。

**如何移除**

到 **設定 → 裝置與服務**刪除本整合，再用 HACS 移除下載，或刪除 `/config/custom_components/incipio_commandkit/` 後重新啟動 Core。原 HomeKit Device 配對仍由原整合管理。

## 開發驗證

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q custom_components tests
```

11 個測試使用模擬 HA coordinator／HomeKit connection，驗證 UUID 解析、可讀權限、連線重新載入、IIDs 改變、登記清理、異常值及韌體 characteristic 不被額外輪詢／寫入。GitHub Actions 重跑相同的離線測試與語法檢查；不代表 HAOS 實機驗證。

原生介面依據：[Core 2026.9.4 HomeKit connection](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/components/homekit_controller/connection.py)、[Core coordinator](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/helpers/update_coordinator.py)、[HomeKit Device 文件](https://www.home-assistant.io/integrations/homekit_controller/)。

## License

[MIT](LICENSE)。
