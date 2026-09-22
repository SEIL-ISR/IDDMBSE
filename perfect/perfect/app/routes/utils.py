def fill_specification_kwargs(spec, kwargs: dict):
    if isinstance(spec, str) and spec.startswith("$"):
        try:
            try:
                return float(kwargs[spec[1:]])
            except ValueError:
                return kwargs[spec[1:]]
        except KeyError:
            raise KeyError(f"Template argument '{spec[1:]}' not defined")
    if isinstance(spec, list):
        return [fill_specification_kwargs(v, kwargs) for v in spec]
    if isinstance(spec, dict):
        return {k: fill_specification_kwargs(v, kwargs) for k, v in spec.items()}
    return spec
