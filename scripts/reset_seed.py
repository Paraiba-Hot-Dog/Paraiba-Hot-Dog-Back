"""Reseta os dados do banco e aplica a seed de desenvolvimento."""

from scripts.seed import run


if __name__ == "__main__":
    run()
    print("Banco resetado e seeds aplicados com sucesso.")
