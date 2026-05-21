import 'package:flutter/cupertino.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:agroamigo_iphone/services/images.dart';

/// Port of `ProductImage` from `ProductImage.tsx`.
/// Loads the product-specific Supabase image and falls back to the
/// category-level Unsplash placeholder on error.
class ProductImage extends StatefulWidget {
  ProductImage({
    super.key,
    this.productName,
    this.categoryName,
    double? width,
    double? height,
    double? size,
    this.fit = BoxFit.cover,
    BorderRadius? borderRadius,
    double? radius,
  })  : width = width ?? size,
        height = height ?? size,
        borderRadius = borderRadius ??
            (radius != null ? BorderRadius.circular(radius) : null);

  final String? productName;
  final String? categoryName;
  final double? width;
  final double? height;
  final BoxFit fit;
  final BorderRadius? borderRadius;

  @override
  State<ProductImage> createState() => _ProductImageState();
}

class _ProductImageState extends State<ProductImage> {
  late String _uri;
  late String _fallback;

  @override
  void initState() {
    super.initState();
    _uri = getProductImageUrl(productName: widget.productName, categoryName: widget.categoryName);
    _fallback = getProductFallbackUrl(widget.categoryName);
  }

  @override
  void didUpdateWidget(ProductImage old) {
    super.didUpdateWidget(old);
    if (old.productName != widget.productName ||
        old.categoryName != widget.categoryName) {
      setState(() {
        _uri = getProductImageUrl(productName: widget.productName, categoryName: widget.categoryName);
        _fallback = getProductFallbackUrl(widget.categoryName);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: widget.borderRadius ?? BorderRadius.zero,
      child: CachedNetworkImage(
        imageUrl: _uri,
        width: widget.width,
        height: widget.height,
        fit: widget.fit,
        errorWidget: (_, __, ___) {
          if (_uri != _fallback) {
            // Schedule URI swap after the current build frame.
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted) setState(() => _uri = _fallback);
            });
          }
          return CachedNetworkImage(
            imageUrl: _fallback,
            width: widget.width,
            height: widget.height,
            fit: widget.fit,
            errorWidget: (_, __, ___) => SizedBox(
              width: widget.width,
              height: widget.height,
            ),
          );
        },
      ),
    );
  }
}

/// Port of `InsumoImage` from `ProductImage.tsx`.
/// Loads the insumo-specific image and falls back to the insumo fallback URL.
class InsumoImage extends StatefulWidget {
  const InsumoImage({
    super.key,
    this.insumoName,
    this.subgrupo,
    this.width,
    this.height,
    this.fit = BoxFit.cover,
    this.borderRadius,
  });

  final String? insumoName;
  final String? subgrupo;
  final double? width;
  final double? height;
  final BoxFit fit;
  final BorderRadius? borderRadius;

  @override
  State<InsumoImage> createState() => _InsumoImageState();
}

class _InsumoImageState extends State<InsumoImage> {
  late String _uri;
  late String _fallback;

  @override
  void initState() {
    super.initState();
    _uri = getInsumoImageUrl(insumoName: widget.insumoName, subgrupo: widget.subgrupo);
    _fallback = getInsumoFallbackUrl();
  }

  @override
  void didUpdateWidget(InsumoImage old) {
    super.didUpdateWidget(old);
    if (old.insumoName != widget.insumoName ||
        old.subgrupo != widget.subgrupo) {
      setState(() {
        _uri = getInsumoImageUrl(insumoName: widget.insumoName, subgrupo: widget.subgrupo);
        _fallback = getInsumoFallbackUrl();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: widget.borderRadius ?? BorderRadius.zero,
      child: CachedNetworkImage(
        imageUrl: _uri,
        width: widget.width,
        height: widget.height,
        fit: widget.fit,
        errorWidget: (_, __, ___) {
          if (_uri != _fallback) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted) setState(() => _uri = _fallback);
            });
          }
          return CachedNetworkImage(
            imageUrl: _fallback,
            width: widget.width,
            height: widget.height,
            fit: widget.fit,
            errorWidget: (_, __, ___) => SizedBox(
              width: widget.width,
              height: widget.height,
            ),
          );
        },
      ),
    );
  }
}
