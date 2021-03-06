import sys
from os import path
import argparse
from collections import OrderedDict
import numpy as np

sys.path.append('./src/')
from h01_data import Vocab, save_vocabs, save_embeddings
from h01_data.oracle import arc_standard_oracle, arc_eager_oracle
from h01_data.oracle import is_projective, is_good
from utils import utils
from utils import constants


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--language', type=str, required=True)
    parser.add_argument('--data-path', type=str, default='data/')
    parser.add_argument('--glove-file', type=str, required=True)
    parser.add_argument('--min-vocab-count', type=int, default=2)
    parser.add_argument('--transition', type=str, choices=['arc-standard','arc-eager'],default='arc-eager')
    return parser.parse_args()


def get_sentence(file):
    sentence = []
    for line in file:
        tokens = line.strip().split()
        if tokens and tokens[0].isdigit():
            sentence += [tokens]
        elif tokens:
            pass
        else:
            yield sentence
            sentence = []


def process_sentence(sentence, vocabs):
    words, tags, rels = vocabs
    processed = [{
        'word': words.ROOT,
        'word_id': words.ROOT_IDX,
        'tag1': tags.ROOT,
        'tag1_id': tags.ROOT_IDX,
        'tag2': tags.ROOT,
        'tag2_id': tags.ROOT_IDX,
        'head': 0,
        'rel': rels.ROOT,
        'rel_id': rels.ROOT_IDX,
    }]
    heads = []
    relations = []
    rel2id = {}
    for token in sentence:
        processed += [{
            'word': token[1],
            'word_id': words.idx(token[1]),
            'tag1': token[3],
            'tag1_id': tags.idx(token[3]),
            'tag2': token[4],
            'tag2_id': tags.idx(token[4]),
            'head': int(token[6]),
            # 'head_id': token[6],
            'rel': token[7],
            'rel_id': rels.idx(token[7]),
        }]
        heads.append(int(token[6]))
        relations.append(token[7])
        rel2id[token[7]] = rels.idx(token[7])

    return processed, heads, relations, rel2id

def labeled_action_pairs(actions,relations):
    labeled_acts = []
    tmp_rels = relations.copy()

    for act in actions:
        if act == constants.shift or act is None:
            labeled_acts.append((act,-1))
        elif act is not None:
            labeled_acts.append((act,tmp_rels[0]))
            tmp_rels.pop(0)


    return labeled_acts

def process_data(in_fname_base, out_path, mode, vocabs, oracle=None, transition_name=None):
    in_fname = in_fname_base % mode
    out_fname = '%s/%s.json' % (out_path, mode)
    if oracle is not None:
        out_fname_history = '%s/%s_actions_%s.json' % (out_path, transition_name, mode)
        utils.remove_if_exists(out_fname_history)

    utils.remove_if_exists(out_fname)
    print('Processing: %s' % in_fname)

    with open(in_fname, 'r') as file:
        for sentence in get_sentence(file):
            sent_processed, heads, relations,rel2id = process_sentence(sentence, vocabs)
            heads_proper = [0] + heads

            # print(heads_proper)
            # print(relations)
            arc2label = {arc: rel for (arc, rel) in zip(list(range(len(heads))), relations)}
            #relations = ['root'] + relations
            # print(len(heads_proper))
            # print(len(relations))
            sentence_proper = list(range(len(heads_proper)))
            #word2headrels = {w: (h, r) for (w, h, r) in zip(sentence_proper, heads_proper, relations)}
            # print(word2headrels)
            word2head = {w: h for (w, h) in zip(sentence_proper, heads_proper)}
            if is_projective(word2head):
                actions,relations_order = oracle(sentence_proper, word2head,relations)
                relation_ids = [rel2id[rel] for rel in relations_order]

                #labeled_actions = labeled_action_pairs(actions,relation_ids.copy())
                #actions_processed = {'transition': actions, 'relations':relation_ids,'labeled_actions':labeled_actions}
                actions_processed = {'transition': actions, 'relations':relation_ids,}
                utils.append_json(out_fname_history, actions_processed)
                utils.append_json(out_fname, sent_processed)

            else:
                continue



def add_sentence_vocab(sentence, words, tags, rels):
    for token in sentence:
        words.count_up(token[1])
        tags.count_up(token[3])
        tags.count_up(token[4])
        rels.count_up(token[7])


def process_vocabs(words, tags, rels):
    words.process_vocab()
    tags.process_vocab()
    rels.process_vocab()


def add_embedding_vocab(embeddings, words):
    for word in embeddings.keys():
        words.add_pretrained(word)


def get_vocabs(in_fname_base, out_path, min_count, embeddings=None):
    in_fname = in_fname_base % 'train'
    words, tags, rels = Vocab(min_count), Vocab(min_count), Vocab(min_count)
    print('Getting vocabs: %s' % in_fname)

    with open(in_fname, 'r') as file:
        for sentence in get_sentence(file):
            add_sentence_vocab(sentence, words, tags, rels)

    if embeddings is not None:
        add_embedding_vocab(embeddings, words)

    process_vocabs(words, tags, rels)
    save_vocabs(out_path, words, tags, rels)
    return (words, tags, rels)


def read_embeddings(fname):
    # loading GloVe
    embedd_dim = -1
    embedd_dict = OrderedDict()
    # with gzip.open(fname, 'rt') as file:
    with open(fname, 'r') as file:
        for line in file.readlines():
            line = line.strip()
            if len(line) == 0:
                continue

            tokens = line.split()
            if embedd_dim < 0:
                embedd_dim = len(tokens) - 1
            elif embedd_dim == len(tokens):
                # Skip empty word
                continue
            else:
                assert embedd_dim + 1 == len(tokens), 'Dimension of embeddings should be consistent'

            embedd = np.empty([1, embedd_dim], dtype=np.float32)
            embedd[:] = tokens[1:]
            embedd_dict[tokens[0]] = embedd

    return embedd_dict


def process_embeddings(src_fname, out_path):
    embedding_dict = read_embeddings(src_fname)
    save_embeddings(out_path, embedding_dict)
    return embedding_dict


def main():
    args = get_args()

    in_fname = path.join(args.data_path, constants.UD_LANG_FNAMES[args.language])
    out_path = path.join(args.data_path, constants.UD_PATH_PROCESSED, args.language)
    utils.mkdir(out_path)

    embeddings = process_embeddings(args.glove_file, out_path)

    vocabs = get_vocabs(in_fname, out_path, min_count=args.min_vocab_count, embeddings=embeddings)
    oracle = None
    if args.transition == 'arc-standard':
        oracle = arc_standard_oracle
    elif args.transition == 'arc-eager':
        oracle = arc_eager_oracle

    process_data(in_fname, out_path, 'train', vocabs, oracle, args.transition)
    process_data(in_fname, out_path, 'dev', vocabs, oracle, args.transition)
    process_data(in_fname, out_path, 'test', vocabs, oracle, args.transition)


if __name__ == '__main__':
    main()
