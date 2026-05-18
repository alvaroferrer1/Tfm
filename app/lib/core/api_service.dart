import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import 'supabase_client.dart';

// API_URL se pasa en tiempo de build:
//   flutter run --dart-define=API_URL=http://192.168.1.X:8000/api/v1
//   flutter build apk --dart-define=API_URL=http://192.168.1.X:8000/api/v1
//
// Para la demo: usa la IP local del ordenador donde corre el backend.
// Comandos rápidos:
//   Windows: ipconfig | findstr IPv4
//   Mac/Linux: ifconfig | grep "inet "
//
// Si no se pasa, usa localhost (solo válido en emulador Android, no en dispositivo real).
const _baseUrl = String.fromEnvironment(
  'API_URL',
  defaultValue: 'http://10.0.2.2:8000/api/v1', // 10.0.2.2 = localhost desde emulador Android
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
    final resp = await http.post(
      Uri.parse('$_baseUrl/brief/run'),
      headers: _headers,
    ).timeout(const Duration(seconds: 120));
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
    await http.post(
      Uri.parse('$_baseUrl/actions/complete'),
      headers: _headers,
      body: jsonEncode({
        'action_id': actionId,
        'completed_by': completedBy,
        'notes': notes,
        'photo_url': photoUrl,
      }),
    ).timeout(const Duration(seconds: 15));
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
