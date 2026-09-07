import 'package:agroamigo_iphone/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('only the exact HTTPS Azure origin stays inside the app', () {
    expect(isAppUrl(Uri.parse('$appOrigin/farm')), isTrue);
    expect(isAppUrl(Uri.parse('$appOrigin/api/evidence/id/content')), isTrue);
    for (final unsafe in [
      'http://agroamigo-demo-9a04.azurewebsites.net/farm',
      'https://agroamigo-demo-9a04.azurewebsites.net.evil.example/farm',
      'https://evil.example/?next=$appOrigin',
      'https://agroamigo-demo-9a04.azurewebsites.net:444/farm',
      'https://user@agroamigo-demo-9a04.azurewebsites.net/farm',
      'file:///etc/passwd',
      'javascript:alert(1)',
      'agroamigo-export://scenario?data=%7B%7D',
    ]) {
      expect(isAppUrl(Uri.parse(unsafe)), isFalse, reason: unsafe);
    }
  });
}
