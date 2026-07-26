#!/bin/bash
echo "=================================================="
echo "    INSTALADOR DO RASTREADOR - TERMUX PYTHON     "
echo "=================================================="
echo ""

echo "[1/3] Atualizando repositórios e instalando pacotes base..."
pkg update -y && pkg install -y python termux-api jq git

echo ""
echo "[2/3] Instalando bibliotecas Python necessárias..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "[3/3] Garantindo permissões do Termux API..."
echo "Certifique-se de que o aplicativo 'Termux:API' está instalado no seu Android e com permissão de Localização concedida."

echo ""
echo "=================================================="
echo " Instalação concluída com sucesso!"
echo " Para iniciar o sistema, execute: python termux_app.py"
echo "=================================================="
