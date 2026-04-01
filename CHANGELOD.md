### Fixed
- Filtering for flag `eb_supervisora == True` changed to `eb_supervisora == "1"` when loading `configs.db.silver.cadastro_sysgrid` in `01-silver/03.1-medidas`
- SIGD-QS filtering was being done by `max_execution_date`, now it's being done with reference to `configs.param.datetoprocess.configs.param.datetoprocess.month:02d` in `01-silver/03.2-eventos`

the quote:
> teste