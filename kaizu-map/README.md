# 岸釣り海図マップ v1.0

公開URL: https://kurenn46-max.github.io/aori-catch-map/kaizu-map/

スマホのChromeでURLを開く。HTMLプレビューではなく、GitHub Pages（HTTPS）で利用する。

## 機能
- 小浜・舞鶴・常神・高浜・越前への移動、指で移動、拡大縮小
- 国土地理院の標準地図と航空写真の切り替え
- 沿岸海域土地条件図（ccm1/ccm2）を半透明で重ねる。沿岸調査図が整備されている地域に限る
- OpenSeaMapの航路標識（**水深情報ではない**）
- GPSによる現在地表示（許可が必要）
- 地図上の2点間の距離測定
- 中心地点のポイントをブラウザのlocalStorageに保存、CSV書き出し。ポイントは公開GitHubにアップロードされない

## 岸際の水深について
沿岸調査図には水深線・水深点・底質などが収録されている地域があるが、日本全域ではない。表示レイヤーの最大原解像度はズーム16。ズーム17〜18では画像を拡大するだけなので、測量精度は上がらない。海底の局所的な岩、沈み根、浅瀬を表示・保証するものではない。釣り場へ行くときは立入規制・海況を現地で確認し、航海には最新の公式海図を用いること。

## 参照・利用条件
- 国土地理院の地理院タイル: https://maps.gsi.go.jp/development/ichiran.html
- 沿岸海域土地条件図の概要: https://www.gsi.go.jp/bousaichiri/engan14.html
- OpenSeaMap: https://www.openseamap.org/

画像タイルの閲覧にはネット接続が必要。このHTMLは外部JavaScriptライブラリなしで動作する。元の釣果マップ（リポジトリ直下のindex.html）は変更していない。
