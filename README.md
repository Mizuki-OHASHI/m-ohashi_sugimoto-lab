# Source code distribution

Sugimoto lab.

## 環境構築

> Mac/Linux 向けです.
> Windows の場合は WSL2 の利用を推奨します.

1. python3 のインストール

2. 仮想環境の作成 (ディレクトリ `./venv` が作成されるはず)
    ```sh
    python3 -m venv venv
    ```

3. 仮想環境の起動 (**これは毎回行う**)
    ```sh
    source ./venv/bin/activate
    ```

4. 依存関係のインストール
    ```sh
    pip install -r ./requirements.txt
    ```

> **Note**: NGSolve のインストールに問題がある場合は [NGSolve 公式ドキュメント](https://ngsolve.org/installation.html) を参照。
