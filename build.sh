#!/bin/bash
BUILD_DIR=$1
GIT_BRANCH=$2
#VERSION=`echo "$2" | sed -e "s/.*\/release\///g"`
#BUILDFILE=${BUILD_DIR}/makeitso-${VERSION}.tgz
BUILDFILE=${BUILD_DIR}/makeitso.tgz

if [[ -z $BUILD_DIR ]]
then
  echo "Fail: Please provide build directory as the first parameter"
  exit 1
fi

if [[ -z $GIT_BRANCH ]]
then
  echo "Fail: Please provide git branch as the second parameter"
  exit 1
fi

MYDIR=$(dirname "${BASH_SOURCE[0]}" )
tar zcvf $BUILDFILE $MYDIR/*
