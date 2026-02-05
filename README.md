## 環境構築

1. python3 のインストール
2. 仮想環境の作成
    ```sh
    python3 -m venv venv
    ```
    ディレクトリ `./venv` が作成されるはず
3. 仮想環境の起動 (**これは毎回行う**)
    ```sh
    source ./venv/bin/activate
    ```
4. 依存関係のインストール
    ```sh
    pip install -r ./requirements.txt
    ```

