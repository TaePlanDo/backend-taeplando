# Szerokie eksperymenty

Uruchamiaj z katalogu backendu, np.:

```powershell
.\.venv\Scripts\python.exe -m app.experiments run --config experiments/konfiguracje-szerokie/07-limit-czasu.json
```

Podmień nazwę pliku, aby uruchomić kolejną rundę. Każdy plik porównuje jeden
parametr z domyślną konfiguracją. Dla jednego scenariusza (7–13 lat, 60 minut,
15 uczestników, dostępny sprzęt: pałki, preferowany typ: technika) każdy wariant to 10 prób.
Raport Markdown i JSON powstają w `experiments/results`.

| Plik | Badany parametr | Wartość produkcyjna |
|---|---|---:|
| 01-mutacja.json | Prawdopodobieństwo mutacji | 0,35 |
| 02-krzyzowanie.json | Prawdopodobieństwo krzyżowania | 0,70 |
| 03-populacja.json | Wielkość populacji | 50 |
| 04-generacje.json | Maksymalna liczba generacji | 100 |
| 05-turniej.json | Wielkość turnieju | 4 |
| 06-zmiana-czasu.json | Maksymalny krok mutacji czasu w minutach | 5 |
| 07-limit-czasu.json | Dopuszczalne odchylenie czasu ćwiczenia w % | 20 |
| 08-rodzaje-mutacji.json | Względne wagi czterech rodzajów mutacji | 1:1:1:1 |
| 09-tolerancja-nadmiaru.json | Tolerancja przekroczenia czasu segmentu | 0,05 |
| 10-tolerancja-niedoboru.json | Tolerancja niedoboru czasu segmentu | 0,2 |
| 11-tolerancja-trudnosci.json | Tolerancja odchylenia trudności | 1 |
| 12-tolerancja-obciazenia.json | Tolerancja odchylenia obciążenia ciała | 1 |
| 13-cel-fizyczny.json | Docelowa trudność fizyczna | 2,5 |
| 14-cel-techniczny.json | Docelowa trudność techniczna | 2,5 |
| 15-cel-gora.json | Docelowe obciążenie góry ciała | 2,5 |
| 16-cel-dol.json | Docelowe obciążenie dołu ciała | 2,5 |
| 17-cel-korpus.json | Docelowe obciążenie korpusu | 2,5 |
| 18-okno-oceny.json | Długość okna oceny w minutach | 5 |

Parametry 09–18 zmieniają sposób obliczania ocen fitness. Wysokości ocen
składowych między takimi wariantami nie są wprost porównywalne. Dobór wartości
docelowych powinien także uwzględniać potrzeby grup i ocenę trenera. Limity czasu
oraz obciążenie komputera mogą ograniczać liczbę wykonanych generacji.

Każda runda używa domyślnych wartości pozostałych parametrów. Po wybraniu
nowych wartości należy wpisać je do kolejnych wariantów, jeśli chcesz sprawdzić
ich działanie łącznie. Dotychczasowe raporty nie zmieniają ustawień generatora.
