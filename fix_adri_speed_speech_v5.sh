#!/usr/bin/env bash
# ============================================================
# ADRI SPEED SPEECH — v5 (corrección robusta por patrones)
# ============================================================
# Por qué existe esta versión: los scripts anteriores (v3/v4) se
# probaron contra una copia reconstruida del proyecto que, según el
# log de error que compartieron, NO coincide exactamente con el
# código real en disco (probablemente por ediciones manuales o de
# otra herramienta desde entonces). Buscar texto EXACTO para
# reemplazar falla si el archivo real difiere aunque sea en un
# espacio. Este script usa patrones flexibles (regex) que encuentran
# el código roto sin importar el formato exacto alrededor.
#
# Ejecutar desde la raíz del proyecto:
#   chmod +x fix_adri_speed_speech_v5.sh
#   ./fix_adri_speed_speech_v5.sh
#
# Corrige exactamente los errores del log compartido:
#   - database.dart: columna llamada "text" choca con el método
#     text() heredado de Drift (bug real que introduje yo en v3 y
#     nunca se detectó por no tener compilador Dart a mano). Se
#     reescribe completo, sin tabla ChatMessages (igual que v4).
#   - main.dart: se quita el Provider<AppDatabase> que dependía de
#     la tabla eliminada.
#   - chat_screen.dart: se quitan las llamadas a
#     ChatMessagesCompanion/_db.insertChatMessage (por patrón, no
#     texto exacto), y se corrige speakResponse(response) ->
#     speakResponse(response.cleanText) donde aparezca.
#
# NO TOCA el problema de _speechService.listen(...) con
# onLanguageDetected faltante -- no pude verlo con suficiente
# contexto en el log como para tocarlo sin arriesgar romper otra
# cosa. Al final del script te digo la línea exacta a agregar a mano
# (es una sola línea).
# ============================================================
set -euo pipefail

LIB="lib"
BACKUP_SUFFIX=".bak5_$(date +%Y%m%d_%H%M%S)"
backup() { cp "$1" "$1$BACKUP_SUFFIX"; }

# ------------------------------------------------------------
# 1) database.dart — reescritura completa (self-contained, no
#    depende de nada del archivo anterior).
# ------------------------------------------------------------
echo "==> 1/3  database.dart — reescritura completa (quita ChatMessages y el choque de nombres)"
backup "$LIB/core/services/database.dart"
cat > "$LIB/core/services/database.dart" << 'EOF'
import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;
import 'dart:io';

part 'database.g.dart';

class VocabularyItems extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get word => text().withLength(min: 1, max: 120)();
  TextColumn get definition => text()();
  TextColumn get translation => text().nullable()();
  TextColumn get exampleSentence => text().nullable()();
  TextColumn get phonetic => text().nullable()();
  TextColumn get semanticGroup => text().nullable()();

  RealColumn get easeFactor => real().withDefault(const Constant(2.5))();
  IntColumn get intervalDays => integer().withDefault(const Constant(0))();
  IntColumn get repetitions => integer().withDefault(const Constant(0))();

  DateTimeColumn get nextReview => dateTime().withDefault(currentDateAndTime)();
  DateTimeColumn get lastReviewed => dateTime().nullable()();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
}

class SessionSnapshots extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get sessionId => text().withLength(min: 1, max: 100)();
  TextColumn get metadataJson => text()();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
}

@DriftDatabase(tables: [VocabularyItems, SessionSnapshots])
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(_openConnection());

  @override
  int get schemaVersion => 1;

  Future<List<VocabularyItem>> getWordsToReview(DateTime currentDate) {
    return (select(vocabularyItems)
          ..where((tbl) => tbl.nextReview.isSmallerOrEqualValue(currentDate)))
        .get();
  }

  Future<int> insertOrUpdateVocabulary(VocabularyItemsCompanion item) {
    return into(vocabularyItems).insertOnConflictUpdate(item);
  }

  Future<void> updateSrsData(
    int id,
    double newEaseFactor,
    int newInterval,
    int newRepetitions,
    DateTime nextReviewDate,
  ) {
    return (update(vocabularyItems)..where((tbl) => tbl.id.equals(id))).write(
      VocabularyItemsCompanion(
        easeFactor: Value(newEaseFactor),
        intervalDays: Value(newInterval),
        repetitions: Value(newRepetitions),
        nextReview: Value(nextReviewDate),
        lastReviewed: Value(DateTime.now()),
      ),
    );
  }

  Future<int> deleteVocabulary(int id) {
    return (delete(vocabularyItems)..where((tbl) => tbl.id.equals(id))).go();
  }

  Future<int> saveSessionSnapshot(SessionSnapshotsCompanion snapshot) {
    return into(sessionSnapshots).insertOnConflictUpdate(snapshot);
  }

  Future<SessionSnapshot?> getLastSessionSnapshot(String sessionId) {
    return (select(sessionSnapshots)
          ..where((tbl) => tbl.sessionId.equals(sessionId))
          ..orderBy([(tbl) => OrderingTerm(expression: tbl.createdAt, mode: OrderingMode.desc)])
          ..limit(1))
        .getSingleOrNull();
  }
}

LazyDatabase _openConnection() {
  return LazyDatabase(() async {
    final dbFolder = await getApplicationDocumentsDirectory();
    final file = File(p.join(dbFolder.path, 'lingua_core.sqlite'));
    return NativeDatabase(file);
  });
}
EOF

# ------------------------------------------------------------
# 2) main.dart — quitar el Provider<AppDatabase>(...) por patrón,
#    sin importar el formato exacto de indentación/espacios.
# ------------------------------------------------------------
echo "==> 2/3  main.dart — quitar Provider<AppDatabase> (por patrón)"
backup "$LIB/main.dart"
python3 - "$LIB/main.dart" << 'PYEOF'
import re, sys
path = sys.argv[1]
s = open(path, encoding='utf-8').read()
before = s

# Quita el bloque Provider<AppDatabase>( ... ), completo, sin
# importar espacios/saltos de línea internos.
s = re.sub(
    r"\s*Provider<AppDatabase>\(\s*create:\s*\(_\)\s*=>\s*AppDatabase\(\),\s*"
    r"dispose:\s*\(_,\s*db\)\s*=>\s*db\.close\(\),\s*\),",
    "",
    s,
    flags=re.DOTALL,
)

# Si quedó un import de database.dart y ya no se usa AppDatabase en
# ningún otro lado del archivo, lo quitamos también.
if "AppDatabase" not in s:
    s = re.sub(r"import '[^']*core/services/database\.dart';\n", "", s)

if s != before:
    open(path, 'w', encoding='utf-8').write(s)
    print("main.dart: Provider<AppDatabase> eliminado.")
else:
    print("AVISO: no se encontró el patrón de Provider<AppDatabase> en main.dart; revisar a mano.", file=sys.stderr)
PYEOF

# ------------------------------------------------------------
# 3) chat_screen.dart — quitar referencias a Drift por patrón +
#    corregir speakResponse(response) -> speakResponse(response.cleanText)
# ------------------------------------------------------------
echo "==> 3/3  chat_screen.dart — quitar referencias a Drift (por patrón) + fix de speakResponse"
backup "$LIB/features/vocabulary/presentation/screens/chat_screen.dart"
python3 - "$LIB/features/vocabulary/presentation/screens/chat_screen.dart" << 'PYEOF'
import re, sys
path = sys.argv[1]
s = open(path, encoding='utf-8').read()
changes = []

# a) imports de Drift/database.dart, cualquier variante de espacios
new_s = re.sub(r"import '[^']*core/services/database\.dart';\n", "", s)
new_s = re.sub(r"import 'package:drift/drift\.dart'[^;]*;\n", "", new_s)
if new_s != s:
    changes.append("imports de Drift eliminados")
s = new_s

# b) campo `late AppDatabase _db;` (cualquier espaciado)
new_s = re.sub(r"[ \t]*late AppDatabase _db;\n", "", s)
if new_s != s:
    changes.append("campo _db eliminado")
s = new_s

# c) `_db = context.read<AppDatabase>();`
new_s = re.sub(r"[ \t]*_db\s*=\s*context\.read<AppDatabase>\(\);\n", "", s)
if new_s != s:
    changes.append("inicialización de _db eliminada")
s = new_s

# d) cualquier llamada `_db.insertChatMessage(ChatMessagesCompanion.insert( ... ));`
#    (con o sin `await`/`unawaited(...)` alrededor), hasta el primer `;` que la
#    cierra. IMPORTANTE: hay que absorber también el `await` previo o queda
#    un `await` colgado sin expresión (error de sintaxis).
pattern_insert = re.compile(
    r"[ \t]*(?:await\s+)?(?:unawaited\()?_db\.insertChatMessage\(\s*ChatMessagesCompanion\.insert\("
    r"[^;]*?\)\)\)?;\n?",
    re.DOTALL,
)
new_s, n = pattern_insert.subn("", s)
if n:
    changes.append(f"{n} llamada(s) a _db.insertChatMessage eliminadas")
s = new_s

# e) también por si quedó getRecentChatMessages / clearChatHistory sueltos
s = re.sub(r"[ \t]*.*_db\.getRecentChatMessages\([^;]*?;\n?", "", s, flags=re.DOTALL)
s = re.sub(r"[ \t]*.*_db\.clearChatHistory\([^;]*?;\n?", "", s, flags=re.DOTALL)

# f) speakResponse(response) -> speakResponse(response.cleanText)
#    (solo si NO viene ya con .cleanText o .text detrás)
new_s = re.sub(r"speakResponse\(response\)", "speakResponse(response.cleanText)", s)
if new_s != s:
    changes.append("speakResponse(response) -> speakResponse(response.cleanText)")
s = new_s

open(path, 'w', encoding='utf-8').write(s)
if changes:
    print("chat_screen.dart actualizado: " + "; ".join(changes) + ".")
else:
    print("AVISO: no se encontró ningún patrón conocido en chat_screen.dart; revisar a mano.", file=sys.stderr)
PYEOF

echo ""
echo "============================================================"
echo " v5 aplicado. Copias de seguridad con sufijo $BACKUP_SUFFIX"
echo ""
echo " QUEDA UN ERROR QUE NO TOQUÉ A PROPÓSITO (necesito ver más"
echo " contexto para no arriesgar romper otra cosa):"
echo ""
echo "   lib/features/vocabulary/presentation/screens/chat_screen.dart:66"
echo "   'Required named parameter onLanguageDetected must be provided'"
echo ""
echo " Abre ese archivo, busca el bloque que empieza con:"
echo "     _speechService.listen("
echo " y agrégale esta línea dentro de los paréntesis (junto a los"
echo " demás parámetros como language: u onResult:):"
echo ""
echo "     onLanguageDetected: (_) {},"
echo ""
echo " Si prefieres, pégame el bloque completo de ese _speechService.listen(...)"
echo " tal como está en tu archivo y te preparo el parche exacto."
echo ""
echo " Siguiente paso: flutter clean && flutter pub get && flutter run"
echo "============================================================"
