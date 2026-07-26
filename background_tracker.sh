#!/bin/bash
# ==============================================================================
# DAEMON DE RASTREAMENTO GPS 24/7 PARA TERMUX (ANDROID)
# Mantém a CPU ativa com termux-wake-lock e envia atualizações a cada 5s
# ==============================================================================

termux-wake-lock 2>/dev/null

USERNAME="${1:-admin}"
DB_URL="https://rastreador-c229f-default-rtdb.firebaseio.com"

termux-notification -t "📍 Rastreamento GPS 24/7 Ativo" -c "Dispositivo: $USERNAME | Atualizando a cada 5s" --priority high 2>/dev/null

echo "=================================================="
echo " ⚡ DAEMON DE RASTREAMENTO 24/7 INICIADO "
echo " Dispositivo: $USERNAME"
echo " Firebase: $DB_URL"
echo "=================================================="
echo " O processo continuará rodando mesmo com a tela apagada."
echo " Para encerrar este serviço: killall bash"
echo "=================================================="

# Atualiza status no Firebase para ON
curl -s -X PATCH "$DB_URL/users/$USERNAME.json" -H "Content-Type: application/json" -d '{"tracking_enabled": true}' > /dev/null

while true; do
    LAT=""
    LNG=""

    # 1ª Tentativa: Leitura do Termux API GPS
    LOC_RAW=$(termux-location -p gps -s once 2>/dev/null)
    if [ -n "$LOC_RAW" ]; then
        LAT=$(echo "$LOC_RAW" | jq -r '.latitude // empty' 2>/dev/null)
        LNG=$(echo "$LOC_RAW" | jq -r '.longitude // empty' 2>/dev/null)
        ACC=$(echo "$LOC_RAW" | jq -r '.accuracy // 10' 2>/dev/null)
        SPEED=$(echo "$LOC_RAW" | jq -r '.speed // 0' 2>/dev/null)
        ALT=$(echo "$LOC_RAW" | jq -r '.altitude // 0' 2>/dev/null)
    fi

    # 2ª Tentativa: Leitura Nativa do Android OS (cmd location)
    if [ -z "$LAT" ] || [ "$LAT" = "null" ] || [ "$LAT" = "0.0" ]; then
        CMD_RAW=$(cmd location get-last-location 2>/dev/null)
        if [ -n "$CMD_RAW" ]; then
            LAT=$(echo "$CMD_RAW" | grep -oP '(-?\d+\.\d+)' | head -n 1)
            LNG=$(echo "$CMD_RAW" | grep -oP '(-?\d+\.\d+)' | sed -n '2p')
            ACC=12
            SPEED=0
            ALT=0
        fi
    fi

    NOW=$(date "+%d/%m/%Y %H:%M:%S")

    # Se capturou coordenadas válidas, envia para o Firebase
    if [ -n "$LAT" ] && [ -n "$LNG" ] && [ "$LAT" != "null" ]; then
        # Reverse Geocode via Nominatim
        GEO_RAW=$(curl -s -A "TermuxDaemon/1.0" "https://nominatim.openstreetmap.org/reverse?format=json&lat=$LAT&lon=$LNG&zoom=18&addressdetails=1" 2>/dev/null)
        
        ROAD=$(echo "$GEO_RAW" | jq -r '.address.road // .address.pedestrian // "Rua não identificada"' 2>/dev/null)
        HNUM=$(echo "$GEO_RAW" | jq -r '.address.house_number // ""' 2>/dev/null)
        SUBURB=$(echo "$GEO_RAW" | jq -r '.address.neighbourhood // .address.suburb // "Bairro não identificado"' 2>/dev/null)
        CITY=$(echo "$GEO_RAW" | jq -r '.address.city // .address.town // .address.municipality // "Cidade não identificada"' 2>/dev/null)
        STATE=$(echo "$GEO_RAW" | jq -r '.address.state // ""' 2>/dev/null)
        
        STREET="$ROAD"
        if [ -n "$HNUM" ] && [ "$ROAD" != "Rua não identificada" ]; then
            STREET="$ROAD, $HNUM"
        fi

        MAPS_URL="https://www.google.com/maps?q=$LAT,$LNG"

        PAYLOAD=$(jq -n \
            --arg un "$USERNAME" \
            --arg st "$STREET" \
            --arg sb "$SUBURB" \
            --arg ct "$CITY" \
            --arg uf "$STATE" \
            --arg url "$MAPS_URL" \
            --arg ts "$NOW" \
            --argjson lat "$LAT" \
            --argjson lng "$LNG" \
            --argjson acc "$ACC" \
            --argjson sp "$SPEED" \
            --argjson alt "$ALT" \
            '{
                username: $un,
                latitude: $lat,
                longitude: $lng,
                accuracy: $acc,
                speed: $sp,
                altitude: $alt,
                street: $st,
                neighborhood: $sb,
                city: $ct,
                state: $uf,
                google_maps_url: $url,
                last_updated: $ts,
                monitoring_active: true,
                provider: "termux_shell_daemon"
            }')

        curl -s -X PATCH "$DB_URL/locations/$USERNAME.json" \
             -H "Content-Type: application/json" \
             -d "$PAYLOAD" > /dev/null
    fi

    sleep 5
done
