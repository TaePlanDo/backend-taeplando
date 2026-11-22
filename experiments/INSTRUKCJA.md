# Laboratorium generatora planów

Uruchamiaj polecenia z katalogu `backend-taeplando`. Potrzebne są środowisko
projektu, skonfigurowany `DATABASE_URL` i działająca baza PostgreSQL. Laboratorium
odczytuje aktywne konfiguracje ćwiczeń jednego trenera w transakcji tylko do
odczytu. Nie tworzy w bazie zadań, grup ani planów. Grupę, schemat, historię
i plany tworzy w pamięci; jeden raport na sesję zapisuje na dysku.

## Uruchomienie

```powershell
.\.venv\Scripts\python.exe -m app.experiments run
```

Domyślny plik ustawień to `experiments/session.json`. Aby użyć innego:

```powershell
.\.venv\Scripts\python.exe -m app.experiments run --config experiments/session.json
```

Na koniec program wypisze ścieżkę raportu w `experiments/results`. Każde
uruchomienie tworzy JSON i czytelny raport Markdown o tej samej nazwie. Przy wielu trenerach z aktywnymi ćwiczeniami
program wypisze ich identyfikatory; wpisz wybrany UUID jako `trainer_id`.
Przy jednym trenerze `null` wybiera go automatycznie. Pobierane są jego aktywne
konfiguracje, w tym prywatne i globalne; brakujące konfiguracje globalne nie są
automatycznie tworzone w bazie.

Uruchamia się jeden scenariusz, a liczbę prób ustala `plans_per_scenario` razy
liczba konfiguracji. To może potrwać długo. Do sprawdzenia konfiguracji przed sesją ustaw
tymczasowo `plans_per_scenario` na 1, małą `population_size` i
`max_generations`, a następnie przywróć docelowe wartości.

## Ustawienia

Edytuj plik JSON; prawdopodobieństwa zapisuj jako ułamki, np. `0.25` oznacza
25%. Pierwsza konfiguracja w przykładzie odpowiada obecnym wartościom algorytmu.
Każda konfiguracja może mieć pola:

| Pole | Znaczenie | Domyślnie |
|---|---|---:|
| `name` | Unikalna nazwa widoczna w raporcie | wymagane |
| `population_size` | Wielkość populacji początkowej segmentu | 50 |
| `max_generations` | Maksymalna liczba generacji | 100 |
| `crossover_probability` | Prawdopodobieństwo krzyżowania | 0.70 |
| `mutation_probability` | Prawdopodobieństwo wywołania mutacji osobnika | 0.35 |
| `tournament_size` | Liczba osobników w turnieju | 4 |
| `mutation_duration_delta` | Maksymalna zmiana czasu przy mutacji, w minutach | 5 |
| `duration_deviation_percent` | Limit odchylenia od domyślnego czasu ćwiczenia, w procentach | 20 |
| `mutation_mode_weights` | Względne wagi wyboru: zmiana czasu, zamiana, dodanie, przetasowanie | `[1, 1, 1, 1]` |

Limit jest stosowany podczas mutacji, oceny poprawności osobnika i końcowej
walidacji planu. Odchylenie jest zaokrąglane do najbliższej minuty; dla
niezerowego limitu wynosi co najmniej minutę, ale ćwiczenie jednominutowe
pozostaje jednominutowe. Limit 0% pozostawia domyślny czas każdego ćwiczenia.
Większy limit w laboratorium nie zmienia produkcyjnej walidacji 20%.

Obiekt `fitness` w wariancie pozwala zmienić parametry poszczególnych ocen:
`duration_over_sigma_ratio`, `duration_under_sigma_ratio`, `difficulty_sigma`,
`body_load_sigma`, `physical_difficulty_demand`, `technical_difficulty_demand`,
`body_upper_demand`, `body_lower_demand`, `body_core_demand` i
`window_time_size`. Pominięte wartości pozostają domyślne. Wagi między
składowymi fitness nie są tu zmieniane. Oceny obliczone z różnymi parametrami
fitness nie muszą mieć tej samej interpretacji, dlatego sama wyższa ocena nie
oznacza, że powstał lepszy plan.

Gotowe konfiguracje są w `experiments/konfiguracje-szerokie` (opis i kolejność
w pliku `README.md`). Liczba trzech planów historii jest nadal stała w
laboratorium i w produkcyjnym generatorze; nie jest jednym z tych parametrów.

Pola wspólne to: `plans_per_scenario`, `seed`, `timeout_seconds`,
`history_exercises_per_plan`, `trainer_id` i `output_dir`. Konfiguracje
korzystają z tych samych scenariuszy, seedów i historii. `seed` pozwala
powtórzyć losowanie przy niezmienionych danych. Limit czasu jest wspólny dla
segmentów pojedynczego planu. Algorytm sprawdza go między generacjami, więc nie
jest to twarde przerwanie w dokładnej sekundzie; liczba przypadków, w których
został osiągnięty, jest widoczna w raporcie. Przy limicie zależnym od czasu
wynik może się różnić zależnie od obciążenia komputera.

Laboratorium używa jednego scenariusza: grupy 7–13 lat i 60-minutowego planu
(rozgrzewka 20%, rozciąganie 10%, ćwiczenia 40%, zabawa 30%):

| Grupa | Uczestnicy | Sprzęt | Preferowany typ |
|---|---:|---|---|
| 7–13 lat | 15 | Pałki | Technika |

Listy sprzętu i typów są w `src/app/experiments/lab.py`. Wyniki dotyczą tego
jednego scenariusza i nie pokazują działania dla innych grup ani sprzętu.

## Odczyt i ocena

Otwórz raport `.md` w podglądzie Markdown, aby zobaczyć porównanie oraz
przykładowy plan i jego oceny fitness dla każdego scenariusza i konfiguracji.
Plan jest najbliższy średnim ośmiu składowych fitness w danym scenariuszu:
wybieramy najmniejszą sumę kwadratów różnic, z równą wagą składowych.
Nie oznacza to, że jest najlepszy. Poprzednie raporty JSON nie zawierają
wszystkich planów, więc nie można na ich podstawie odtworzyć takiego wyboru.

Szczegóły są w raporcie JSON. Na początku znajduje się
`kandydaci_do_oceny` i `porownanie`, a poniżej wyniki oraz przykładowy
plan dla każdego scenariusza i konfiguracji. Wyniki dotyczą wszystkich prób, nie tylko
przykładowego planu. Szczegóły scenariuszy podają liczbę kandydatów, błędy i ich
przyczyny. Jeśli nie uda się wygenerować planu, pola średnich dla niego nie
istnieją; błędy są liczone osobno.

Lista kandydatów jest pomocą w nawigacji: najpierw wybiera konfiguracje
z najmniejszą liczbą niepowodzeń, a następnie odrzuca te, dla których inna
konfiguracja ma zarówno nie większe średnie odchylenie czasu, jak i nie większy
udział `repeat_1`, przy przynajmniej jednej wartości mniejszej. Jest to prosta
selekcja według tych dwóch metryk, nie ocena statystyczna ani decyzja trenera.
Uwzględnij również inne parametry, rozrzut i przypadki trudne. Dane wszystkich
konfiguracji pozostają w raporcie.

Najważniejsze pola wyników (`srednia`, `mediana`, `p90` to odpowiednio średnia,
mediana i 90. percentyl po planach):

| Pole | Znaczenie |
|---|---|
| `proby`, `poprawne`, `bledy` | Liczby prób i wyników walidacji |
| `duration_deviation_minutes` | Bezwzględne odchylenie łącznego czasu planu od docelowego, w minutach |
| `duration_seconds` | Czas generowania planu, w sekundach |
| `exercises` | Liczba wystąpień ćwiczeń w planie |
| `repeat_1` | Udział wystąpień z ostatniego mockowanego treningu |
| `repeat_2_3` | Udział wystąpień ostatnio użytych 2–3 treningi temu |
| `repeat_4_plus` | Udział niewystępujących w ostatnich trzech treningach |
| `duration_time`, `physical_difficulty`, `technical_difficulty`, `body_balance`, `age_coverage`, `training_type`, `equipment_usage`, `recent_usage` | Składowe fitness z generatora, w zakresie 0–1; średnie segmentów ważone czasem |

Wartości udziałów są średnimi udziałów w poszczególnych planach; `0.25` oznacza
25%. Dla braku preferowanego typu lub sprzętu odpowiednie kryterium fitness
wynosi 1 zgodnie z implementacją generatora i nie oznacza rzeczywistego
dopasowania typu czy wykorzystania sprzętu. Plan przykładowy ma pole `ostatnio`:
1–3 oznacza odległość, a 4 oznacza brak w trzech ostatnich treningach, nie
koniecznie dokładnie cztery treningi temu.

Historia to trzy niezależne losowe próbki po maksymalnie
`history_exercises_per_plan` ćwiczeń z puli dostępnej dla danego scenariusza;
najnowsze wystąpienie wygrywa. Jest syntetyczna, nie odzwierciedla faktycznej
historii trenera ani nie jest aktualizowana między próbnymi planami. Tę samą
historię i seedy stosuje się do porównywanych konfiguracji. Tak jak w produkcji,
dopasowanie wieku wymaga przecięcia zakresów wieku, a nie pełnego pokrycia.

Możesz uzupełnić `ocena_trenera` przy wybranych konfiguracjach bezpośrednio
w raporcie, zachowując prawidłowy JSON: `true` / `false`, ocena 1–5 i komentarz
w cudzysłowie. Wybierz konfigurację na podstawie podsumowania i swojej oceny.
Żeby dostać propozycję kolejnej rundy mutacji wokół niej:

```powershell
.\.venv\Scripts\python.exe -m app.experiments suggest --report experiments/results/NAZWA_PLIKU.json --name mutacja-25 --step 0.01
```

Polecenie wypisze proponowany JSON dla pięciu wartości wokół wskazanej; skopiuj
go do pliku konfiguracji i uruchom `run` ponownie. Twój wybór nazwy jest krokiem
human-in-the-loop — program nie interpretuje automatycznie komentarza. Nie
nadpisuje poprzedniego raportu. Gdy różnice wyników są małe, zwiększ liczbę prób
i sprawdź rozrzut; narzędzie nie wylicza przedziałów ufności i nie dowodzi, że
25% jest statystycznie lepsze od 26%.
