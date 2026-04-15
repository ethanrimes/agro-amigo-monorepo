'use client';

import React, { useState } from 'react';
import { getProductImageUrl, getProductFallbackUrl, getInsumoImageUrl, getInsumoFallbackUrl } from '@agroamigo/shared';

interface ProductImageProps {
  productName?: string;
  categoryName?: string;
  style?: React.CSSProperties;
  className?: string;
}

export function ProductImage({ productName, categoryName, style, className }: ProductImageProps) {
  const primaryUri = getProductImageUrl(productName, categoryName);
  const fallbackUri = getProductFallbackUrl(categoryName);
  const [uri, setUri] = useState(primaryUri);

  return (
    <img
      src={uri}
      alt={productName || 'Product'}
      className={className}
      style={{ objectFit: 'cover', ...style }}
      onError={() => {
        if (uri !== fallbackUri) setUri(fallbackUri);
      }}
    />
  );
}

interface InsumoImageProps {
  insumoName?: string;
  subgrupo?: string;
  style?: React.CSSProperties;
}

export function InsumoImage({ insumoName, subgrupo, style }: InsumoImageProps) {
  const primaryUri = getInsumoImageUrl(insumoName, subgrupo);
  const fallbackUri = getInsumoFallbackUrl();
  const [uri, setUri] = useState(primaryUri);

  return (
    <img
      src={uri}
      alt={insumoName || 'Insumo'}
      style={{ objectFit: 'cover', ...style }}
      onError={() => {
        if (uri !== fallbackUri) setUri(fallbackUri);
      }}
    />
  );
}
