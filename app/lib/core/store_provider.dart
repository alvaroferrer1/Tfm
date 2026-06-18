import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'supabase_client.dart';

// Código guardado en onboarding (SharedPreferences)
final _savedStoreCodeProvider = FutureProvider<String?>((ref) async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getString('user_store_id');
});

// Resuelve el store_id con esta prioridad:
// 1. user_metadata de Supabase (multi-tenant real en producción)
// 2. Código introducido en el onboarding (SharedPreferences)
// 3. Constante del .env (fallback demo)
final resolvedStoreIdProvider = Provider<String>((ref) {
  final meta = Supabase.instance.client.auth.currentUser?.userMetadata;
  final fromMeta = meta?['store_id'] as String?;
  if (fromMeta != null && fromMeta.isNotEmpty) return fromMeta;
  final fromPrefs = ref.watch(_savedStoreCodeProvider).valueOrNull;
  if (fromPrefs != null && fromPrefs.isNotEmpty) return fromPrefs;
  return storeId;
});

// Nombre de la tienda: user_metadata.store_name → env STORE_NAME → 'Mi Supermercado'
final resolvedStoreNameProvider = Provider<String>((ref) {
  final meta = Supabase.instance.client.auth.currentUser?.userMetadata;
  final fromMeta = meta?['store_name'] as String?;
  return (fromMeta != null && fromMeta.isNotEmpty) ? fromMeta : storeName;
});

// URL del plano subido por el encargado (guardado en SharedPreferences)
final mapImageUrlProvider = FutureProvider<String?>((ref) async {
  final sid = ref.watch(resolvedStoreIdProvider);
  final prefs = await SharedPreferences.getInstance();
  return prefs.getString('map_image_url_$sid');
});

// Persiste la URL del plano tras la subida
Future<void> saveMapImageUrl(String sid, String url) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString('map_image_url_$sid', url);
}

Future<void> clearMapImageUrl(String sid) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.remove('map_image_url_$sid');
}
