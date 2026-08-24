// Smoke test for the ATLAS companion app.
//
// The app is not a counter app, so this verifies that the root widget boots
// its startup shell without throwing. SharedPreferences is mocked so the
// startup lookup resolves cleanly under test.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:companion_app/main.dart';

void main() {
  testWidgets('AtlasApp builds its startup shell', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});

    await tester.pumpWidget(AtlasApp());
    // Allow the SharedPreferences lookup in StartupGate to resolve.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(MaterialApp), findsOneWidget);
  });
}
