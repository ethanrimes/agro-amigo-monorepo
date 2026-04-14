import React, { useState } from 'react';
import { Image, ImageStyle, StyleProp } from 'react-native';
import { getProductImageUrl, getProductFallbackUrl, getInsumoImageUrl, getInsumoFallbackUrl } from '../lib/images';

interface ProductImageProps {
  productName?: string;
  categoryName?: string;
  style?: StyleProp<ImageStyle>;
}

/**
 * Product image with automatic fallback.
 * Tries the product-specific Supabase image first; on error falls back to
 * category-level Unsplash placeholder.
 */
export function ProductImage({ productName, categoryName, style }: ProductImageProps) {
  const primaryUri = getProductImageUrl(productName, categoryName);
  const fallbackUri = getProductFallbackUrl(categoryName);
  const [uri, setUri] = useState(primaryUri);

  return (
    <Image
      source={{ uri }}
      style={style}
      onError={() => {
        if (uri !== fallbackUri) {
          setUri(fallbackUri);
        }
      }}
    />
  );
}

interface InsumoImageProps {
  insumoName?: string;
  subgrupo?: string;
  style?: StyleProp<ImageStyle>;
}

/**
 * Insumo image with automatic fallback.
 */
export function InsumoImage({ insumoName, subgrupo, style }: InsumoImageProps) {
  const primaryUri = getInsumoImageUrl(insumoName, subgrupo);
  const fallbackUri = getInsumoFallbackUrl();
  const [uri, setUri] = useState(primaryUri);

  return (
    <Image
      source={{ uri }}
      style={style}
      onError={() => {
        if (uri !== fallbackUri) {
          setUri(fallbackUri);
        }
      }}
    />
  );
}
