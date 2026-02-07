from afl_predictions.data import load_data

def main():
    df = load_data.list_cached_matches('data/raw/cache')
    print('cached matches total:', len(df))
    if not df.empty:
        print(df[['token','url']].head(50).to_string())

if __name__ == '__main__':
    main()
