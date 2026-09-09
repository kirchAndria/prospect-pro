#!/bin/bash
# Lanceur de la Machine de Prospection
cd /home/kirch/project/prospection-tool || exit 1

echo "=========================================="
echo "  MACHINE DE PROSPECTION"
echo "=========================================="
echo ""
echo "Navigateur pour l'extraction des avis :"
echo "  1) Chromium dedie Playwright (defaut - recommande)"
echo "  2) Brave"
echo "  3) Chrome"
read -p "Ton choix [1] : " choix

case "$choix" in
  2) export NAV_TYPE="brave" ;;
  3) export NAV_TYPE="chrome" ;;
  *) export NAV_TYPE="playwright" ;;
esac

echo ""
echo "Navigateur choisi : $NAV_TYPE"
echo "Demarrage de l'interface..."
echo ""

if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate.fish
elif [ -f venv/bin/activate ]; then
  source venv/bin/activate
fi

streamlit run prospection_app.py
