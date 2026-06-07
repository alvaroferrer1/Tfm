import 'package:supabase_flutter/supabase_flutter.dart';

SupabaseClient get supabase => Supabase.instance.client;

const storeId = 'demo-store-001';
const storeName = String.fromEnvironment('STORE_NAME', defaultValue: 'Super Martínez');
