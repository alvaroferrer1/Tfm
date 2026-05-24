import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import 'supabase_client.dart';

// API_URL se pasa en tiempo de build:
//   flutter run -d chrome --dart-define=API_URL=http://localhost:8001/api/v1
//   flutter run -d android --dart-define=API_URL=http://10.0.2.2:8001/api/v1  (emulador)
//   flutter run -d android --dart-define=API_URL=http://192.168.1.X:8001/api/v1 (dispositivo real)
//
// El default es localhost — válido para demo web en Chrome en el mismo ordenador.
const _baseUrl = String.fromEnvironment(
  'API_URL',
  defaultValue: 'http://localhost:8001/api/v1',
);

class ApiService {
  static final _instance = ApiService._();
  factory ApiService() => _instance;
  ApiService._();

  Map<String, String> get _headers {
    final session = Supabase.instance.client.auth.currentSession;
    return {
      'Content-Type': 'application/json',
      if (session != null) 'Authorization': 'Bearer ${session.accessToken}',
    };
  }

  Future<Map<String, dynamic>> scan(String barcode) async {
    final userId = supabase.auth.currentUser?.id ?? '';
    final resp = await http.post(
      Uri.parse('$_baseUrl/scan'),
      headers: _headers,
      body: jsonEncode({
        'barcode': barcode,
        'user_id': userId,
      }),
    ).timeout(const Duration(seconds: 45));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> getDashboard() async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/dashboard'),
      headers: _headers,
    ).timeout(const Duration(seconds: 15));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> runBrief() async {
    // Usa el endpoint síncrono: espera resultado completo, no requiere auth,
    // más robusto para demo que el background task que puede sillar.
    final resp = await http.post(
      Uri.parse('$_baseUrl/brief/run/sync'),
      headers: _headers,
    ).timeout(const Duration(seconds: 150));
    return _parse(resp);
  }

  Future<List<Map<String, dynamic>>> getActions() async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/actions'),
      headers: _headers,
    ).timeout(const Duration(seconds: 15));
    final data = _parse(resp);
    return List<Map<String, dynamic>>.from(data['actions'] ?? data);
  }

  Future<void> completeAction({
    required String actionId,
    required String completedBy,
    String notes = '',
    String photoUrl = '',
  }) async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/actions/complete'),
      headers: _headers,
      body: jsonEncode({
        'action_id': actionId,
        'completed_by': completedBy,
        'notes': notes,
        'photo_url': photoUrl,
      }),
    ).timeout(const Duration(seconds: 15));
    if (resp.statusCode >= 400) {
      throw Exception('Error completando acción: ${resp.statusCode} ${resp.body}');
    }
  }

  Future<List<Map<String, dynamic>>> getDailyBriefsList({int limit = 14}) async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/reports/daily-list?limit=$limit'),
      headers: _headers,
    ).timeout(const Duration(seconds: 15));
    final data = _parse(resp);
    return List<Map<String, dynamic>>.from(data['briefs'] ?? []);
  }

  Future<List<Map<String, dynamic>>> getSupplierStats() async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/stats/suppliers'),
      headers: _headers,
    ).timeout(const Duration(seconds: 15));
    final data = _parse(resp);
    return List<Map<String, dynamic>>.from(data['suppliers'] ?? []);
  }

  Future<Map<String, dynamic>> getDonationStats({int days = 30}) async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/stats/donations?days=$days'),
      headers: _headers,
    ).timeout(const Duration(seconds: 15));
    return _parse(resp);
  }

  Future<List<Map<String, dynamic>>> getStoresComparison() async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/stats/comparison'),
      headers: _headers,
    ).timeout(const Duration(seconds: 15));
    final data = _parse(resp);
    return List<Map<String, dynamic>>.from(data['stores'] ?? []);
  }

  Future<Map<String, dynamic>> importBatches(String csvData) async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/import/batches'),
      headers: _headers,
      body: jsonEncode({'csv_data': csvData}),
    ).timeout(const Duration(seconds: 30));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> getCurrentUser() async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/user/me'),
      headers: _headers,
    ).timeout(const Duration(seconds: 10));
    return _parse(resp);
  }

  Future<void> linkTelegram(String telegramUserId) async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/user/link-telegram'),
      headers: _headers,
      body: jsonEncode({'telegram_user_id': telegramUserId}),
    ).timeout(const Duration(seconds: 10));
    if (resp.statusCode >= 400) {
      throw Exception('API error ${resp.statusCode}: ${resp.body}');
    }
  }

  Future<void> unlinkTelegram() async {
    final resp = await http.delete(
      Uri.parse('$_baseUrl/user/link-telegram'),
      headers: _headers,
    ).timeout(const Duration(seconds: 10));
    if (resp.statusCode >= 400) {
      throw Exception('API error ${resp.statusCode}: ${resp.body}');
    }
  }

  Future<Map<String, dynamic>> runMonthlyReport() async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/reports/monthly/run'),
      headers: _headers,
    ).timeout(const Duration(seconds: 120));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> advanceDemo({int days = 1, bool generateBrief = false}) async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/demo/advance'),
      headers: _headers,
      body: jsonEncode({'days': days, 'generate_brief': generateBrief}),
    ).timeout(const Duration(seconds: 60));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> resetDemo() async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/demo/reset'),
      headers: _headers,
    ).timeout(const Duration(seconds: 60));
    return _parse(resp);
  }

  Future<List<Map<String, dynamic>>> getOrderSuggestions() async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/stats/order-suggestions'),
      headers: _headers,
    ).timeout(const Duration(seconds: 15));
    final data = _parse(resp);
    return List<Map<String, dynamic>>.from(data['suggestions'] ?? []);
  }

  Future<Map<String, dynamic>> getEsgStats({int days = 30}) async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/stats/esg?days=$days'),
      headers: _headers,
    ).timeout(const Duration(seconds: 20));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> getEsgReport({int days = 30}) async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/stats/esg/report?days=$days'),
      headers: _headers,
    ).timeout(const Duration(seconds: 60));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> getRiskPredictions({int days = 7}) async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/predict/risk?days=$days'),
      headers: _headers,
    ).timeout(const Duration(seconds: 20));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> getPredictionBrief({int days = 5}) async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/predict/brief?days=$days'),
      headers: _headers,
    ).timeout(const Duration(seconds: 60));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> analyzeProductImage({
    required String imageBase64,
    String productName = '',
    int daysLeft = -1,
    String category = '',
  }) async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/scan/vision'),
      headers: _headers,
      body: jsonEncode({
        'image_base64': imageBase64,
        'product_name': productName,
        'days_left': daysLeft,
        'category': category,
      }),
    ).timeout(const Duration(seconds: 45));
    return _parse(resp);
  }

  // ── Fase 5: Agent activity endpoints ────────────────────────────────────────

  Future<Map<String, dynamic>> getAgentStatus() async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/agent/status'),
      headers: _headers,
    ).timeout(const Duration(seconds: 10));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> getAgentActivity() async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/agent/activity'),
      headers: _headers,
    ).timeout(const Duration(seconds: 10));
    return _parse(resp);
  }

  Future<List<Map<String, dynamic>>> getAgentConversations({int limit = 20}) async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/agent/conversations?limit=$limit'),
      headers: _headers,
    ).timeout(const Duration(seconds: 10));
    final data = _parse(resp);
    return List<Map<String, dynamic>>.from(data['conversations'] ?? []);
  }

  Future<List<Map<String, dynamic>>> getAgentRuns({int limit = 20}) async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/agent/runs?limit=$limit'),
      headers: _headers,
    ).timeout(const Duration(seconds: 10));
    final data = _parse(resp);
    return List<Map<String, dynamic>>.from(data['runs'] ?? []);
  }

  Future<Map<String, dynamic>> getSupervisorDecisions({int limit = 50}) async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/agent/decisions?limit=$limit'),
      headers: _headers,
    ).timeout(const Duration(seconds: 10));
    return _parse(resp);
  }

  Future<Map<String, dynamic>> getTelegramStatus() async {
    final resp = await http.get(
      Uri.parse('$_baseUrl/telegram/status'),
      headers: _headers,
    ).timeout(const Duration(seconds: 10));
    return _parse(resp);
  }

  Future<void> notifyAppLogin() async {
    try {
      await http.post(
        Uri.parse('$_baseUrl/user/app-login-notify'),
        headers: _headers,
      ).timeout(const Duration(seconds: 10));
    } catch (_) {
      // Non-critical — ignore failures silently
    }
  }

  /// Descarga el PDF del brief de hoy y devuelve los bytes.
  Future<List<int>> downloadBriefPdf({String date = ''}) async {
    final uri = Uri.parse('$_baseUrl/reports/brief/pdf${date.isNotEmpty ? '?date=$date' : ''}');
    final resp = await http.get(uri, headers: _headers).timeout(const Duration(seconds: 30));
    if (resp.statusCode >= 200 && resp.statusCode < 300) {
      return resp.bodyBytes;
    }
    throw Exception('Error descargando brief PDF: ${resp.statusCode}');
  }

  /// Descarga el PDF del informe semanal y devuelve los bytes.
  Future<List<int>> downloadWeeklyPdf({String weekStart = ''}) async {
    final uri = Uri.parse('$_baseUrl/reports/weekly/pdf${weekStart.isNotEmpty ? '?week_start=$weekStart' : ''}');
    final resp = await http.get(uri, headers: _headers).timeout(const Duration(seconds: 60));
    if (resp.statusCode >= 200 && resp.statusCode < 300) {
      return resp.bodyBytes;
    }
    throw Exception('Error descargando informe semanal PDF: ${resp.statusCode}');
  }

  /// Descarga el PDF del informe mensual y devuelve los bytes.
  Future<List<int>> downloadMonthlyPdf() async {
    final uri = Uri.parse('$_baseUrl/reports/monthly/pdf');
    final resp = await http.get(uri, headers: _headers).timeout(const Duration(seconds: 90));
    if (resp.statusCode >= 200 && resp.statusCode < 300) {
      return resp.bodyBytes;
    }
    throw Exception('Error descargando informe mensual PDF: ${resp.statusCode}');
  }

  /// Envía un PDF al backend y devuelve el análisis de Claude.
  Future<Map<String, dynamic>> analyzePdfReport(List<int> pdfBytes, String filename) async {
    final uri = Uri.parse('$_baseUrl/reports/analyze-pdf');
    final request = http.MultipartRequest('POST', uri)
      ..headers.addAll(_headers)
      ..files.add(http.MultipartFile.fromBytes(
        'file',
        pdfBytes,
        filename: filename,
      ));
    final streamed = await request.send().timeout(const Duration(seconds: 120));
    final resp = await http.Response.fromStream(streamed);
    return _parse(resp);
  }

  Map<String, dynamic> _parse(http.Response resp) {
    if (resp.statusCode >= 200 && resp.statusCode < 300) {
      final decoded = jsonDecode(resp.body);
      if (decoded is Map<String, dynamic>) return decoded;
      return {'data': decoded};
    }
    throw Exception('API error ${resp.statusCode}: ${resp.body}');
  }
}

final api = ApiService();
