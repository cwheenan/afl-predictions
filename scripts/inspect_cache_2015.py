from afl_predictions.data import load_data

def main():
    df = load_data.list_cached_matches('data/raw/cache')
    df2015 = df[df['url'].str.contains('/2015/')]
    print('cached 2015 matches total:', len(df2015))
    if not df2015.empty:
        print(df2015[['token','url']].to_string(index=False))

if __name__ == '__main__':
    main()
