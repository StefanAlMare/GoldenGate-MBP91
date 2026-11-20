# Run after verifying the Golden B volume, hardware and console user.
display_reference
display_rc=$?
echo 'Prima citire a modulelor din bara de meniu.'
gg_menu_items
first_rc=$?
gg_menubar_metal_state
printf '\nPe MacBook, deschide o dată meniul Wi-Fi sau Bluetooth din zona simbolului lipsă, apoi închide-l. Ai 25 de secunde.\n'
start=$(/bin/date '+%F %T%z') || exit 3
/bin/sleep 25
end=$(/bin/date '+%F %T%z') || exit 3
echo 'A doua citire a modulelor din bara de meniu.'
gg_menu_items
second_rc=$?
gg_menubar_window 'Interacțiunea cu bara de meniu' "$start" "$end"
log_rc=$?
gg_menubar_window 'Serviciile de compilare în același interval' "$start" "$end" compiler
compiler_rc=$?
printf 'GG_MENIU coduri ecrane=%s module_înainte=%s module_după=%s jurnal=%s compilator=%s\n' "$display_rc" "$first_rc" "$second_rc" "$log_rc" "$compiler_rc"
# A complete log query with no matching events returns 4.
if (( display_rc || first_rc || second_rc || (log_rc != 0 && log_rc != 4) || (compiler_rc != 0 && compiler_rc != 4) )); then
    echo 'Captură parțială. Păstrează raportul pentru interpretarea secțiunilor disponibile.'
    exit 3
fi
