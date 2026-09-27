import 'dart:convert';
import 'dart:io';
import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  await integrationDriver(
    writeResponseOnFailure: true,
    responseDataCallback: (data) async {
      final directory =
          Platform.environment['AGRO_IOS_TEST_ARTIFACTS'] ?? '../../artifacts';
      final file = File('$directory/report.json');
      await file.parent.create(recursive: true);
      // PNGs are written by onScreenshot. Avoid duplicating every byte as a
      // decimal JSON array (hundreds of MB for a full source audit).
      final report = Map<String, dynamic>.from(data ?? {});
      final screenshots = report['screenshots'];
      if (screenshots is List) {
        report['screenshots'] = screenshots.map((shot) {
          if (shot is! Map) return shot;
          return Map<String, dynamic>.from(shot)..remove('bytes');
        }).toList();
      }
      await file.writeAsString(
        const JsonEncoder.withIndent('  ').convert(report),
      );
    },
    onScreenshot: (name, bytes, [args]) async {
      final directory =
          Platform.environment['AGRO_IOS_TEST_ARTIFACTS'] ?? '../../artifacts';
      final file = File('$directory/$name.png');
      await file.parent.create(recursive: true);
      await file.writeAsBytes(bytes);
      return true;
    },
  );
}
